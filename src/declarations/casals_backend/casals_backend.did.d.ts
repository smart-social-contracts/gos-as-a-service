import type { IDL } from "@dfinity/candid";

export const idlFactory: IDL.InterfaceFactory;
export interface _SERVICE {
  'list_subnets' : () => Promise<string>,
}
