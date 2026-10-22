/**
 * Demo realms for local/empty-registry preview.
 * Used when list_realms() returns nothing so the globe redesign can be exercised.
 */

export const DUMMY_REALMS = [
  {
    id: 'aaaaa-aa',
    name: 'Berlin Commons',
    realm_name: 'Berlin Commons',
    manifesto: 'A cooperative governance experiment rooted in the heart of Europe.',
    realm_stage: 'production',
    users_count: 420,
    created_at: Math.floor(Date.now() / 1000) - 86400 * 120,
    url: '',
  },
  {
    id: 'bbbbb-bb',
    name: 'Tokyo Mesh',
    realm_name: 'Tokyo Mesh',
    manifesto: 'Neighborhood-scale decision making across the Greater Tokyo Area.',
    realm_stage: 'beta',
    users_count: 1280,
    created_at: Math.floor(Date.now() / 1000) - 86400 * 60,
    url: '',
  },
  {
    id: 'ccccc-cc',
    name: 'São Paulo Agora',
    realm_name: 'São Paulo Agora',
    manifesto: 'Civic coordination for South America’s largest metro.',
    realm_stage: 'alpha',
    users_count: 310,
    created_at: Math.floor(Date.now() / 1000) - 86400 * 30,
    url: '',
  },
  {
    id: 'ddddd-dd',
    name: 'Nairobi Nexus',
    realm_name: 'Nairobi Nexus',
    manifesto: 'East African innovation network for shared public goods.',
    realm_stage: 'beta',
    users_count: 540,
    created_at: Math.floor(Date.now() / 1000) - 86400 * 45,
    url: '',
  },
  {
    id: 'eeeee-ee',
    name: 'San Francisco Collective',
    realm_name: 'San Francisco Collective',
    manifesto: 'Bay Area builders coordinating open infrastructure.',
    realm_stage: 'production',
    users_count: 890,
    created_at: Math.floor(Date.now() / 1000) - 86400 * 200,
    url: '',
  },
  {
    id: 'fffff-ff',
    name: 'Sydney Harbour',
    realm_name: 'Sydney Harbour',
    manifesto: 'Coastal stewardship and participatory budgeting down under.',
    realm_stage: 'alpha',
    users_count: 175,
    created_at: Math.floor(Date.now() / 1000) - 86400 * 15,
    url: '',
  },
];

/** @type {Record<string, { realmId: string, realmName: string, zones: object[], totalUsers: number }>} */
export const DUMMY_ZONE_DATA = {
  'aaaaa-aa': {
    realmId: 'aaaaa-aa',
    realmName: 'Berlin Commons',
    zones: [
      { h3_index: '861f1d48fffffff', user_count: 280, location_name: 'Berlin' },
      { h3_index: '861f1880fffffff', user_count: 140, location_name: 'Potsdam' },
    ],
    totalUsers: 420,
  },
  'bbbbb-bb': {
    realmId: 'bbbbb-bb',
    realmName: 'Tokyo Mesh',
    zones: [
      { h3_index: '862f5a367ffffff', user_count: 800, location_name: 'Tokyo' },
      { h3_index: '862f5bd37ffffff', user_count: 480, location_name: 'Yokohama' },
    ],
    totalUsers: 1280,
  },
  'ccccc-cc': {
    realmId: 'ccccc-cc',
    realmName: 'São Paulo Agora',
    zones: [
      { h3_index: '86a8100c7ffffff', user_count: 310, location_name: 'São Paulo' },
    ],
    totalUsers: 310,
  },
  'ddddd-dd': {
    realmId: 'ddddd-dd',
    realmName: 'Nairobi Nexus',
    zones: [
      { h3_index: '867a6e42fffffff', user_count: 540, location_name: 'Nairobi' },
    ],
    totalUsers: 540,
  },
  'eeeee-ee': {
    realmId: 'eeeee-ee',
    realmName: 'San Francisco Collective',
    zones: [
      { h3_index: '86283082fffffff', user_count: 620, location_name: 'San Francisco' },
      { h3_index: '862834717ffffff', user_count: 270, location_name: 'San Jose' },
    ],
    totalUsers: 890,
  },
  'fffff-ff': {
    realmId: 'fffff-ff',
    realmName: 'Sydney Harbour',
    zones: [
      { h3_index: '86be0e35fffffff', user_count: 175, location_name: 'Sydney' },
    ],
    totalUsers: 175,
  },
};
