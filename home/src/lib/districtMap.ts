export type Point = { x: number; y: number };

export type District = {
  code: string;
  name: string;
  provinceCode: string | null;
  provinceName: string | null;
  path: string;
  centroid: Point;
  labelFits: boolean;
  /** Index of this district's province in first-seen order, for CSS hue grouping. */
  provinceIndex: number;
  /** Index of this district among its province's siblings, for CSS shade variation. */
  shadeIndex: number;
};

export type DistrictMapModel = {
  viewBoxWidth: number;
  viewBoxHeight: number;
  padding: number;
  districts: District[];
  coastlinePath: string;
};

type Dict = Record<string, unknown>;
type GeoJson = Dict | null | undefined;

const CONTENT_WIDTH = 480;
const PADDING = 36;
const LABEL_FONT_SIZE = 11;
const LABEL_CHAR_WIDTH_EM = 0.6;
const LABEL_PADDING_PX = 6;
const MIN_LABEL_HEIGHT_PX = 18;

function asDict(value: unknown): Dict {
  return value && typeof value === 'object' ? (value as Dict) : {};
}

function features(collection: GeoJson): Dict[] {
  const list = asDict(collection).features;
  return Array.isArray(list) ? list.filter((f): f is Dict => !!f && typeof f === 'object') : [];
}

/** Every ring in a feature's geometry, honoring both Polygon and MultiPolygon. */
function rings(feature: Dict): number[][][] {
  const geometry = asDict(feature.geometry);
  const coordinates = geometry.coordinates;
  if (geometry.type === 'Polygon' && Array.isArray(coordinates)) return coordinates as number[][][];
  if (geometry.type === 'MultiPolygon' && Array.isArray(coordinates)) {
    return (coordinates as number[][][][]).flat();
  }
  return [];
}

/** Centroid of a polygon ring via the shoelace formula, falling back to the point average for degenerate (zero-area) rings. */
export function ringCentroid(ring: number[][]): Point {
  let area = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < ring.length - 1; i += 1) {
    const [x0, y0] = ring[i];
    const [x1, y1] = ring[i + 1];
    const cross = x0 * y1 - x1 * y0;
    area += cross;
    cx += (x0 + x1) * cross;
    cy += (y0 + y1) * cross;
  }
  area /= 2;
  if (Math.abs(area) < 1e-9) {
    const points = ring.slice(0, -1).length ? ring.slice(0, -1) : ring;
    const x = points.reduce((sum, point) => sum + point[0], 0) / points.length;
    const y = points.reduce((sum, point) => sum + point[1], 0) / points.length;
    return { x, y };
  }
  return { x: cx / (6 * area), y: cy / (6 * area) };
}

/** Whether a name can be set as a legible label inside a box of the given pixel size. */
export function fitsLabel(name: string, boxWidthPx: number, boxHeightPx: number): boolean {
  if (boxHeightPx < MIN_LABEL_HEIGHT_PX) return false;
  const estimatedWidth = name.length * LABEL_CHAR_WIDTH_EM * LABEL_FONT_SIZE + LABEL_PADDING_PX;
  return estimatedWidth <= boxWidthPx;
}

function collectLonLat(collections: GeoJson[]): number[][] {
  const points: number[][] = [];
  for (const collection of collections) {
    for (const feature of features(collection)) {
      for (const ring of rings(feature)) {
        points.push(...ring);
      }
    }
  }
  return points;
}

function boundingBox(points: number[][]) {
  const lons = points.map((p) => p[0]);
  const lats = points.map((p) => p[1]);
  return { minLon: Math.min(...lons), maxLon: Math.max(...lons), minLat: Math.min(...lats), maxLat: Math.max(...lats) };
}

/**
 * Build the map's geometry, laid out from the committed GeoJSON alone (no
 * external basemap or tile service). The viewBox aspect ratio is derived from
 * the actual lon/lat extent of the country, with a latitude correction for
 * longitude scale, rather than forced into an arbitrary fixed canvas size.
 */
export function buildDistrictMap(input: { districts: GeoJson; provinces: GeoJson; country: GeoJson }): DistrictMapModel {
  const districtFeatures = features(input.districts).filter((f) => asDict(f.properties).admin_level === 'district');
  const provinceFeatures = features(input.provinces);
  const provinceNames = new Map<string, string>(
    provinceFeatures.map((f) => [String(asDict(f.properties).admin_code), String(asDict(f.properties).admin_name ?? '')])
  );

  const allPoints = collectLonLat([input.country, input.districts]);
  if (!allPoints.length) {
    return { viewBoxWidth: CONTENT_WIDTH + 2 * PADDING, viewBoxHeight: CONTENT_WIDTH + 2 * PADDING, padding: PADDING, districts: [], coastlinePath: '' };
  }
  const { minLon, maxLon, minLat, maxLat } = boundingBox(allPoints);
  const refLat = ((minLat + maxLat) / 2) * (Math.PI / 180);
  const cosRefLat = Math.cos(refLat);
  const rawWidth = (maxLon - minLon) * cosRefLat || 1;
  const rawHeight = maxLat - minLat || 1;
  const scale = CONTENT_WIDTH / rawWidth;
  const contentHeight = rawHeight * scale;

  function project([lon, lat]: number[]): Point {
    return {
      x: (lon - minLon) * cosRefLat * scale + PADDING,
      y: (maxLat - lat) * scale + PADDING
    };
  }

  function ringPath(ring: number[][]): { path: string; box: { width: number; height: number } } {
    const projected = ring.map(project);
    const xs = projected.map((p) => p.x);
    const ys = projected.map((p) => p.y);
    const path = projected.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ') + ' Z';
    return { path, box: { width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys) } };
  }

  const provinceOrder: string[] = [];
  const provinceShadeCounts = new Map<string, number>();
  const districts: District[] = districtFeatures.map((feature) => {
    const properties = asDict(feature.properties);
    const code = String(properties.admin_code ?? '');
    const rawName = String(properties.admin_name ?? code);
    const name = rawName.replace(/\s+district$/i, '');
    const provinceCode = properties.parent_admin_code != null ? String(properties.parent_admin_code) : null;

    const featureRings = rings(feature);
    const paths = featureRings.map(ringPath);
    const path = paths.map((p) => p.path).join(' ');
    const outerRing = featureRings[0] ?? [];
    const centroidLonLat = outerRing.length ? ringCentroid(outerRing) : { x: 0, y: 0 };
    const centroid = outerRing.length ? project([centroidLonLat.x, centroidLonLat.y]) : centroidLonLat;
    const outerBox = paths[0]?.box ?? { width: 0, height: 0 };

    let provinceIndex = provinceCode ? provinceOrder.indexOf(provinceCode) : -1;
    if (provinceCode && provinceIndex === -1) {
      provinceIndex = provinceOrder.length;
      provinceOrder.push(provinceCode);
    }
    const shadeIndex = provinceCode ? provinceShadeCounts.get(provinceCode) ?? 0 : 0;
    if (provinceCode) provinceShadeCounts.set(provinceCode, shadeIndex + 1);

    return {
      code,
      name,
      provinceCode,
      provinceName: provinceCode ? provinceNames.get(provinceCode) ?? null : null,
      path,
      centroid,
      labelFits: fitsLabel(name, outerBox.width, outerBox.height),
      provinceIndex: Math.max(provinceIndex, 0),
      shadeIndex
    };
  });

  const coastlinePath = features(input.country)
    .flatMap((feature) => rings(feature).map((ring) => ringPath(ring).path))
    .join(' ');

  return {
    viewBoxWidth: CONTENT_WIDTH + 2 * PADDING,
    viewBoxHeight: contentHeight + 2 * PADDING,
    padding: PADDING,
    districts,
    coastlinePath
  };
}
