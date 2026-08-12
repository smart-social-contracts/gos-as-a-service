import type {
  ActorSubclass,
  HttpAgentOptions,
  ActorConfig,
  Agent,
} from "@dfinity/agent";
import type { IDL } from "@dfinity/candid";
import type { Principal } from "@dfinity/principal";

import { _SERVICE } from './casals_backend.did';

export declare const idlFactory: IDL.InterfaceFactory;
export declare const canisterId: string;

export declare interface CreateActorOptions {
  agent?: Agent;
  agentOptions?: HttpAgentOptions;
  actorOptions?: ActorConfig;
}

export declare const createActor: (
  canisterId: string | Principal,
  options?: CreateActorOptions
) => ActorSubclass<_SERVICE>;
