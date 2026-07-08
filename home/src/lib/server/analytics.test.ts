import { describe, expect, it } from 'vitest';
import { analyticsConfig } from './analytics';

describe('analyticsConfig', () => {
  it('stays disabled without an Umami website id', () => {
    expect(analyticsConfig({})).toBeNull();
    expect(analyticsConfig({ UMAMI_WEBSITE_ID: '   ' })).toBeNull();
  });

  it('uses the Registry Stack Umami script by default', () => {
    expect(analyticsConfig({ UMAMI_WEBSITE_ID: 'site-id' })).toEqual({
      scriptUrl: 'https://stats.registrystack.org/script.js',
      websiteId: 'site-id'
    });
  });

  it('keeps the script URL fixed to the origin allowed by CSP', () => {
    expect(analyticsConfig({ UMAMI_WEBSITE_ID: 'site-id', UMAMI_SCRIPT_URL: 'https://stats.example/script.js' })).toEqual({
      scriptUrl: 'https://stats.registrystack.org/script.js',
      websiteId: 'site-id'
    });
  });
});
