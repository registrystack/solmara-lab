import { describe, expect, it } from 'vitest';
import { buildDistrictMap, fitsLabel, ringCentroid } from './districtMap';

function districtFeature(
  code: string,
  name: string,
  parent: string,
  ring: number[][],
  adminLevel = 'district'
) {
  return {
    type: 'Feature',
    properties: { admin_code: code, admin_name: `${name} district`, admin_level: adminLevel, parent_admin_code: parent },
    geometry: { type: 'Polygon', coordinates: [ring] }
  };
}

function provinceFeature(code: string, name: string, ring: number[][]) {
  return {
    type: 'Feature',
    properties: { admin_code: code, admin_name: name, admin_level: 'province', parent_admin_code: null },
    geometry: { type: 'Polygon', coordinates: [ring] }
  };
}

const SQUARE = [
  [79.0, -10.0],
  [79.1, -10.0],
  [79.1, -9.9],
  [79.0, -9.9],
  [79.0, -10.0]
];
const SQUARE_2 = [
  [79.1, -10.0],
  [79.2, -10.0],
  [79.2, -9.9],
  [79.1, -9.9],
  [79.1, -10.0]
];
const SQUARE_3 = [
  [79.0, -10.1],
  [79.1, -10.1],
  [79.1, -10.0],
  [79.0, -10.0],
  [79.0, -10.1]
];

describe('ringCentroid', () => {
  it('finds the center of a simple square', () => {
    expect(ringCentroid([[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]])).toEqual({ x: 1, y: 1 });
  });

  it('falls back to the point average for a degenerate (zero-area) ring', () => {
    // A closed, colinear ring (as GeoJSON rings always are: first point repeats last).
    expect(ringCentroid([[0, 0], [2, 0], [4, 0], [0, 0]])).toEqual({ x: 2, y: 0 });
  });
});

describe('fitsLabel', () => {
  it('fits a short name in a generous box', () => {
    expect(fitsLabel('Ketterin', 120, 100)).toBe(true);
  });

  it('rejects a long name in a narrow box', () => {
    expect(fitsLabel('A Very Long District Name Indeed', 40, 100)).toBe(false);
  });

  it('rejects any label when the box is too short vertically', () => {
    expect(fitsLabel('OK', 200, 4)).toBe(false);
  });
});

describe('buildDistrictMap', () => {
  const districts = {
    type: 'FeatureCollection',
    features: [
      districtFeature('XS-0101', 'Ketterin', 'XS-01', SQUARE),
      districtFeature('XS-0102', 'Ovasse', 'XS-01', SQUARE_2),
      districtFeature('XS-0201', 'Salvet', 'XS-02', SQUARE_3),
      districtFeature('XS-0101-OLD', 'Ketterin old boundary', 'XS-01', SQUARE, 'district_version')
    ]
  };
  const provinces = {
    type: 'FeatureCollection',
    features: [provinceFeature('XS-01', 'Anvela', SQUARE), provinceFeature('XS-02', 'Tolara', SQUARE_3)]
  };
  const country = {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: { admin_code: 'XS', admin_name: 'Republic of Solmara', admin_level: 'country' },
        geometry: { type: 'Polygon', coordinates: [[[79.0, -10.1], [79.2, -10.1], [79.2, -9.9], [79.0, -9.9], [79.0, -10.1]]] }
      }
    ]
  };

  it('drops the historical district_version duplicate', () => {
    const model = buildDistrictMap({ districts, provinces, country });
    expect(model.districts.map((d) => d.code)).toEqual(['XS-0101', 'XS-0102', 'XS-0201']);
  });

  it('looks up each district province by parent_admin_code', () => {
    const model = buildDistrictMap({ districts, provinces, country });
    const ketterin = model.districts.find((d) => d.code === 'XS-0101')!;
    expect(ketterin.provinceName).toBe('Anvela');
    const salvet = model.districts.find((d) => d.code === 'XS-0201')!;
    expect(salvet.provinceName).toBe('Tolara');
  });

  it('groups districts from the same province under the same province index, in first-seen order', () => {
    const model = buildDistrictMap({ districts, provinces, country });
    const [ketterin, ovasse, salvet] = model.districts;
    expect(ketterin.provinceIndex).toBe(ovasse.provinceIndex);
    expect(ketterin.provinceIndex).not.toBe(salvet.provinceIndex);
  });

  it('gives sibling districts in the same province distinct shade indexes', () => {
    const model = buildDistrictMap({ districts, provinces, country });
    const [ketterin, ovasse] = model.districts;
    expect(ketterin.shadeIndex).not.toBe(ovasse.shadeIndex);
  });

  it('builds a closed SVG path per district', () => {
    const model = buildDistrictMap({ districts, provinces, country });
    for (const district of model.districts) {
      expect(district.path.startsWith('M')).toBe(true);
      expect(district.path.trim().endsWith('Z')).toBe(true);
    }
  });

  it('builds one M..Z subpath per polygon ring, including for MultiPolygon geometries', () => {
    const multi = {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { admin_code: 'XS-0301', admin_name: 'Split district', admin_level: 'district', parent_admin_code: 'XS-03' },
          geometry: { type: 'MultiPolygon', coordinates: [[SQUARE], [SQUARE_2]] }
        }
      ]
    };
    const model = buildDistrictMap({ districts: multi, provinces, country });
    const path = model.districts[0].path;
    expect(path.match(/M/g)?.length).toBe(2);
    expect(path.match(/Z/g)?.length).toBe(2);
  });

  it('derives the viewBox aspect ratio from the real lon/lat extent instead of a fixed canvas', () => {
    const model = buildDistrictMap({ districts, provinces, country });
    // Country bbox is a 0.2deg (lon) x 0.2deg (lat) square near lat -10, so the
    // projected content should stay close to square (cos(-10deg) is ~0.985).
    const contentWidth = model.viewBoxWidth - 2 * model.padding;
    const contentHeight = model.viewBoxHeight - 2 * model.padding;
    expect(contentHeight / contentWidth).toBeGreaterThan(0.9);
    expect(contentHeight / contentWidth).toBeLessThan(1.1);
  });

  it('flags whether each district name fits inside its own rendered shape', () => {
    const model = buildDistrictMap({ districts, provinces, country });
    for (const district of model.districts) {
      expect(typeof district.labelFits).toBe('boolean');
    }
  });

  it('renders a coastline path from the country geometry', () => {
    const model = buildDistrictMap({ districts, provinces, country });
    expect(model.coastlinePath.startsWith('M')).toBe(true);
  });

  it('returns an empty model without throwing when there are no districts', () => {
    const model = buildDistrictMap({ districts: { type: 'FeatureCollection', features: [] }, provinces, country });
    expect(model.districts).toEqual([]);
  });
});
