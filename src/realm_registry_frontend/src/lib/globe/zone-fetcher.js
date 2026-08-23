import { ZONE_DATA_RESOLUTION } from './globe-config.js';
import { isTerritoryZone } from './hex-data.js';

export function isLocalDevelopment() {
  if (typeof window === 'undefined') return false;
  return window.location.hostname.includes('localhost') || window.location.hostname.includes('127.0.0.1');
}

function getAgentHost() {
  return isLocalDevelopment()
    ? `http://localhost:${window.location.port || '4943'}`
    : 'https://icp0.io';
}

/**
 * @param {object[]} realms
 */
export async function fetchRealmDetails(realms) {
  const { Actor, HttpAgent } = await import('@dfinity/agent');
  const { Principal } = await import('@dfinity/principal');
  const { IDL } = await import('@dfinity/candid');

  const statusIdlFactory = ({ IDL: Idl }) => {
    const QuarterInfo = Idl.Record({
      name: Idl.Text,
      canister_id: Idl.Text,
      population: Idl.Nat,
      status: Idl.Text,
      index: Idl.Nat,
      is_capital: Idl.Bool,
    });
    const StatusData = Idl.Record({
      status: Idl.Text,
      test_mode: Idl.Bool,
      transfers_count: Idl.Nat,
      codexes_count: Idl.Nat,
      proposals_count: Idl.Nat,
      realms_count: Idl.Nat,
      version: Idl.Text,
      extensions: Idl.Vec(Idl.Text),
      disputes_count: Idl.Nat,
      commit: Idl.Text,
      instruments_count: Idl.Nat,
      organizations_count: Idl.Nat,
      mandates_count: Idl.Nat,
      tasks_count: Idl.Nat,
      votes_count: Idl.Nat,
      licenses_count: Idl.Nat,
      users_count: Idl.Nat,
      trades_count: Idl.Nat,
      realm_name: Idl.Text,
      realm_manifesto: Idl.Text,
      realm_welcome_message: Idl.Text,
      realm_stage: Idl.Opt(Idl.Text),
      user_profiles_count: Idl.Nat,
      quarters: Idl.Vec(QuarterInfo),
      is_quarter: Idl.Bool,
    });
    const ApiResponse = Idl.Record({
      data: Idl.Variant({ status: StatusData }),
      success: Idl.Bool,
    });
    return Idl.Service({
      status: Idl.Func([], [ApiResponse], ['query']),
    });
  };

  const host = getAgentHost();

  const updates = await Promise.allSettled(
    realms.map(async (realm) => {
      try {
        const agent = new HttpAgent({ host });
        if (isLocalDevelopment()) {
          await agent.fetchRootKey();
        }

        const actor = Actor.createActor(statusIdlFactory, {
          agent,
          canisterId: Principal.fromText(realm.id),
        });

        const response = await actor.status();
        if (response.success && response.data.status) {
          const statusData = response.data.status;
          let usersCount = Number(statusData.users_count);
          // Capital User.count() is capital-residents only; sum quarter directory
          // for federation-wide population (mirrors realm_backend status API).
          if (
            !statusData.is_quarter &&
            Array.isArray(statusData.quarters) &&
            statusData.quarters.length > 0
          ) {
            usersCount = statusData.quarters.reduce(
              (sum, q) => sum + Number(q.population ?? 0),
              0
            );
          }
          return {
            id: realm.id,
            users_count: usersCount,
            manifesto: statusData.realm_manifesto || '',
            realm_name: statusData.realm_name || '',
            realm_stage:
              (Array.isArray(statusData.realm_stage)
                ? statusData.realm_stage[0]
                : statusData.realm_stage) || 'alpha',
          };
        }
      } catch (e) {
        console.warn(`Could not fetch status for ${realm.id}:`, e.message);
      }
      return null;
    })
  );

  return updates
    .filter((r) => r.status === 'fulfilled' && r.value)
    .map((r) => r.value);
}

/**
 * @param {object[]} filteredRealms
 */
export async function fetchZoneData(filteredRealms) {
  const { Actor, HttpAgent } = await import('@dfinity/agent');
  const { Principal } = await import('@dfinity/principal');
  const { IDL } = await import('@dfinity/candid');

  const zonesIdlFactory = ({ IDL: Idl }) =>
    Idl.Service({
      get_zones: Idl.Func([Idl.Nat], [Idl.Text], ['query']),
    });

  const host = getAgentHost();

  const zoneResults = await Promise.allSettled(
    filteredRealms.map(async (realm, index) => {
      try {
        const agent = new HttpAgent({ host });
        if (isLocalDevelopment()) {
          await agent.fetchRootKey();
        }

        const actor = Actor.createActor(zonesIdlFactory, {
          agent,
          canisterId: Principal.fromText(realm.id),
        });

        const response = await actor.get_zones(BigInt(ZONE_DATA_RESOLUTION));
        const data = JSON.parse(response);

        if (data.success && data.zones?.length > 0) {
          const zones = data.zones.filter(isTerritoryZone);
          if (!zones.length) return null;
          return {
            realmId: realm.id,
            realmName: realm.name,
            realmIndex: index,
            zones,
            totalUsers: data.total_users,
          };
        }
      } catch (e) {
        console.warn(`Could not fetch zones for ${realm.name}:`, e.message);
      }
      return null;
    })
  );

  /** @type {Record<string, object>} */
  const realmZoneData = {};
  zoneResults.forEach((result) => {
    if (result.status === 'fulfilled' && result.value) {
      realmZoneData[result.value.realmId] = result.value;
    }
  });

  return realmZoneData;
}
