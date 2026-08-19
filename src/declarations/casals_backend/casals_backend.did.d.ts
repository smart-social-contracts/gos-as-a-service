import type { Principal } from '@dfinity/principal';
import type { ActorMethod } from '@dfinity/agent';
import type { IDL } from '@dfinity/candid';

export interface AccountBalanceArgs { 'account' : Uint8Array | number[] }
export type AccountIdentifier = Uint8Array | number[];
export type Address = string;
export interface Archive { 'canister_id' : Principal }
export interface Archives { 'archives' : Array<Archive> }
export interface AssetCanisterService {
  'grant_permission' : ActorMethod<[GrantPermissionArg], undefined>,
  'store' : ActorMethod<[StoreArg], undefined>,
}
export type AssetPermission = { 'Prepare' : null } |
  { 'ManagePermissions' : null } |
  { 'Commit' : null };
export interface BasiliskIntrospectionService {
  '__browse__' : ActorMethod<[string], string>,
  '__shell__' : ActorMethod<[string], string>,
}
export type BitcoinAddress = string;
export type BitcoinNetwork = { 'Mainnet' : null } |
  { 'Regtest' : null } |
  { 'Testnet' : null };
export interface Block {
  'transaction' : Transaction,
  'timestamp' : TimeStamp,
  'parent_hash' : [] | [Uint8Array | number[]],
}
export type BlockHash = Uint8Array | number[];
export type BlockIndex = bigint;
export interface BlockRange { 'blocks' : Array<Block> }
export interface CanisterSettings {
  'freezing_threshold' : [] | [bigint],
  'controllers' : [] | [Array<Principal>],
  'memory_allocation' : [] | [bigint],
  'compute_allocation' : [] | [bigint],
}
export type CanisterStatus = { 'stopped' : null } |
  { 'stopping' : null } |
  { 'running' : null };
export interface CanisterStatusArgs { 'canister_id' : Principal }
export interface CanisterStatusResult {
  'status' : CanisterStatus,
  'memory_size' : bigint,
  'cycles' : bigint,
  'settings' : DefiniteCanisterSettings,
  'module_hash' : [] | [Uint8Array | number[]],
}
export interface CreateCanisterArgs { 'settings' : [] | [CanisterSettings] }
export interface CreateCanisterResult { 'canister_id' : Principal }
export interface DecimalsResult { 'decimals' : number }
export interface DefiniteCanisterSettings {
  'freezing_threshold' : bigint,
  'controllers' : Array<Principal>,
  'memory_allocation' : bigint,
  'compute_allocation' : bigint,
}
export interface DeleteCanisterArgs { 'canister_id' : Principal }
export interface DepositCyclesArgs { 'canister_id' : Principal }
export type EcdsaCurve = { 'secp256k1' : null };
export interface EcdsaPublicKeyArgs {
  'key_id' : KeyId,
  'canister_id' : [] | [Principal],
  'derivation_path' : Array<Uint8Array | number[]>,
}
export interface EcdsaPublicKeyResult {
  'public_key' : Uint8Array | number[],
  'chain_code' : Uint8Array | number[],
}
export interface FileRegistryService {
  'get_file_chunk_icc' : ActorMethod<[string, string, string, string], string>,
  'get_file_size_icc' : ActorMethod<[string, string], string>,
  'list_files_icc' : ActorMethod<[string], string>,
}
export interface GetBalanceArgs {
  'network' : BitcoinNetwork,
  'address' : string,
  'min_confirmations' : [] | [number],
}
export interface GetBlocksArgs { 'start' : bigint, 'length' : bigint }
export interface GetCurrentFeePercentilesArgs { 'network' : BitcoinNetwork }
export interface GetUtxosArgs {
  'network' : BitcoinNetwork,
  'filter' : [] | [UtxosFilter],
  'address' : string,
}
export interface GetUtxosResult {
  'next_page' : [] | [Uint8Array | number[]],
  'tip_height' : number,
  'tip_block_hash' : Uint8Array | number[],
  'utxos' : Array<Utxo>,
}
export interface GrantPermissionArg {
  'permission' : AssetPermission,
  'to_principal' : Principal,
}
export type GuardResult = { 'Ok' : null } |
  { 'Err' : string };
export interface HttpHeader { 'value' : string, 'name' : string }
export type HttpMethod = { 'get' : null } |
  { 'head' : null } |
  { 'post' : null };
export interface HttpRequestArgs {
  'url' : string,
  'method' : HttpMethod,
  'max_response_bytes' : [] | [bigint],
  'body' : [] | [Uint8Array | number[]],
  'transform' : [] | [HttpTransform],
  'headers' : Array<HttpHeader>,
}
export interface HttpResponse {
  'status' : bigint,
  'body' : Uint8Array | number[],
  'headers' : Array<HttpHeader>,
}
export interface HttpTransform {
  'function' : HttpTransformFunc,
  'context' : Uint8Array | number[],
}
export interface HttpTransformArgs {
  'context' : Uint8Array | number[],
  'response' : HttpResponse,
}
export type HttpTransformFunc = ActorMethod<[HttpTransformArgs], HttpResponse>;
export type InsertError = {
    'ValueTooLarge' : { 'max' : number, 'given' : number }
  } |
  { 'KeyTooLarge' : { 'max' : number, 'given' : number } };
export interface InstallCodeArgs {
  'arg' : Uint8Array | number[],
  'wasm_module' : Uint8Array | number[],
  'mode' : InstallCodeMode,
  'canister_id' : Principal,
}
export type InstallCodeMode = { 'reinstall' : null } |
  { 'upgrade' : null } |
  { 'install' : null };
export interface KeyId { 'name' : string, 'curve' : EcdsaCurve }
export interface KeyTooLarge { 'max' : number, 'given' : number }
export type Memo = bigint;
export type MillisatoshiPerByte = bigint;
export interface NameResult { 'name' : string }
export type NotifyResult = { 'Ok' : null } |
  {
    'Err' : { 'NoError' : null } |
      { 'CanisterError' : null } |
      { 'SysTransient' : null } |
      { 'DestinationInvalid' : null } |
      { 'SysFatal' : null } |
      { 'CanisterReject' : null }
  };
export type Operation = { 'Burn' : Operation_Burn } |
  { 'Mint' : Operation_Mint } |
  { 'Transfer' : Operation_Transfer };
export interface Operation_Burn {
  'from' : Uint8Array | number[],
  'amount' : Tokens,
}
export interface Operation_Mint {
  'to' : Uint8Array | number[],
  'amount' : Tokens,
}
export interface Operation_Transfer {
  'to' : Uint8Array | number[],
  'fee' : Tokens,
  'from' : Uint8Array | number[],
  'amount' : Tokens,
}
export interface Outpoint { 'txid' : Uint8Array | number[], 'vout' : number }
export type Page = Uint8Array | number[];
export interface ProvisionalCreateCanisterWithCyclesArgs {
  'settings' : [] | [CanisterSettings],
  'amount' : [] | [bigint],
}
export interface ProvisionalCreateCanisterWithCyclesResult {
  'canister_id' : Principal,
}
export interface ProvisionalTopUpCanisterArgs {
  'canister_id' : Principal,
  'amount' : bigint,
}
export type QueryArchiveError = {
    'BadFirstBlockIndex' : QueryArchiveError_BadFirstBlockIndex
  } |
  { 'Other' : QueryArchiveError_Other };
export interface QueryArchiveError_BadFirstBlockIndex {
  'requested_index' : bigint,
  'first_valid_index' : bigint,
}
export interface QueryArchiveError_Other {
  'error_message' : string,
  'error_code' : bigint,
}
export type QueryArchiveFn = ActorMethod<[GetBlocksArgs], QueryArchiveResult>;
export type QueryArchiveResult = { 'Ok' : BlockRange } |
  { 'Err' : QueryArchiveError };
export interface QueryBlocksResponse {
  'certificate' : [] | [Uint8Array | number[]],
  'blocks' : Array<Block>,
  'chain_length' : bigint,
  'first_block_index' : bigint,
  'archived_blocks' : Array<QueryBlocksResponse_archived_blocks>,
}
export interface QueryBlocksResponse_archived_blocks {
  'callback' : QueryArchiveFn,
  'start' : bigint,
  'length' : bigint,
}
export type RejectionCode = { 'NoError' : null } |
  { 'CanisterError' : null } |
  { 'SysTransient' : null } |
  { 'DestinationInvalid' : null } |
  { 'SysFatal' : null } |
  { 'CanisterReject' : null };
export type Satoshi = bigint;
export interface SendTransactionArgs {
  'transaction' : Uint8Array | number[],
  'network' : BitcoinNetwork,
}
export type SendTransactionError = { 'QueueFull' : null } |
  { 'MalformedTransaction' : null };
export interface SignWithEcdsaArgs {
  'key_id' : KeyId,
  'derivation_path' : Array<Uint8Array | number[]>,
  'message_hash' : Uint8Array | number[],
}
export interface SignWithEcdsaResult { 'signature' : Uint8Array | number[] }
export type Stable64GrowResult = { 'Ok' : bigint } |
  { 'Err' : { 'OutOfBounds' : null } | { 'OutOfMemory' : null } };
export type StableGrowResult = { 'Ok' : number } |
  { 'Err' : { 'OutOfBounds' : null } | { 'OutOfMemory' : null } };
export type StableMemoryError = { 'OutOfBounds' : null } |
  { 'OutOfMemory' : null };
export interface StartCanisterArgs { 'canister_id' : Principal }
export interface StopCanisterArgs { 'canister_id' : Principal }
export interface StoreArg {
  'key' : string,
  'content' : Uint8Array | number[],
  'sha256' : [] | [Uint8Array | number[]],
  'content_type' : string,
  'content_encoding' : string,
}
export type SubAccount = Uint8Array | number[];
export interface SymbolResult { 'symbol' : string }
export interface TimeStamp { 'timestamp_nanos' : bigint }
export interface Tokens { 'e8s' : bigint }
export interface Transaction {
  'memo' : bigint,
  'operation' : [] | [Operation],
  'created_at_time' : TimeStamp,
}
export interface TransferArgs {
  'to' : Uint8Array | number[],
  'fee' : Tokens,
  'memo' : bigint,
  'from_subaccount' : [] | [Uint8Array | number[]],
  'created_at_time' : [] | [TimeStamp],
  'amount' : Tokens,
}
export type TransferError = { 'TxTooOld' : TransferError_TxTooOld } |
  { 'BadFee' : TransferError_BadFee } |
  { 'TxDuplicate' : TransferError_TxDuplicate } |
  { 'TxCreatedInFuture' : null } |
  { 'InsufficientFunds' : TransferError_InsufficientFunds };
export interface TransferError_BadFee { 'expected_fee' : Tokens }
export interface TransferError_InsufficientFunds { 'balance' : Tokens }
export interface TransferError_TxDuplicate { 'duplicate_of' : bigint }
export interface TransferError_TxTooOld { 'allowed_window_nanos' : bigint }
export interface TransferFee { 'transfer_fee' : Tokens }
export type TransferFeeArg = {};
export type TransferResult = { 'Ok' : bigint } |
  { 'Err' : TransferError };
export interface UninstallCodeArgs { 'canister_id' : Principal }
export interface UpdateSettingsArgs {
  'canister_id' : Principal,
  'settings' : CanisterSettings,
}
export interface Utxo {
  'height' : number,
  'value' : bigint,
  'outpoint' : Outpoint,
}
export type UtxosFilter = { 'Page' : Uint8Array | number[] } |
  { 'MinConfirmations' : number };
export interface ValueTooLarge { 'max' : number, 'given' : number }
export interface _SERVICE {
  '__get_candid_interface_tmp_hack' : ActorMethod<[], string>,
  'add_authorized_wasm' : ActorMethod<[string], string>,
  'apply_arrangement' : ActorMethod<[string], string>,
  'approve_governance_request' : ActorMethod<[string], string>,
  'assign_pool_canister' : ActorMethod<[string], string>,
  'canister_browse' : ActorMethod<[string], string>,
  'canister_exec' : ActorMethod<[string], string>,
  'casals_metadata' : ActorMethod<[], string>,
  'convert_treasury_icp' : ActorMethod<[string], string>,
  'create_canister' : ActorMethod<[string], string>,
  'create_section' : ActorMethod<[string], string>,
  'create_snapshot' : ActorMethod<[string], string>,
  'create_stand' : ActorMethod<[string], string>,
  'delete_arrangement' : ActorMethod<[string], string>,
  'delete_canister' : ActorMethod<[string], string>,
  'delete_principal_alias' : ActorMethod<[string], string>,
  'delete_section' : ActorMethod<[string], string>,
  'delete_stand' : ActorMethod<[string], string>,
  'deploy_sheet' : ActorMethod<[string], string>,
  'destroy_canister' : ActorMethod<[string], string>,
  'destroy_stand' : ActorMethod<[string], string>,
  'estimate_deploy' : ActorMethod<[string], string>,
  'get_arrangement' : ActorMethod<[string], string>,
  'get_canister_deployment' : ActorMethod<[string], string>,
  'get_cycle_history' : ActorMethod<[string], string>,
  'get_cycles' : ActorMethod<[], string>,
  'get_cycles_cached' : ActorMethod<[], string>,
  'get_events' : ActorMethod<[string], string>,
  'get_orchestration_policies' : ActorMethod<[string], string>,
  'get_settings' : ActorMethod<[], string>,
  'get_sheet' : ActorMethod<[], string>,
  'get_status' : ActorMethod<[], string>,
  'get_treasury_flow' : ActorMethod<[string], string>,
  'get_tree' : ActorMethod<[], string>,
  'icrc10_supported_standards' : ActorMethod<[], string>,
  'list_arrangements' : ActorMethod<[], string>,
  'list_authorized_wasms' : ActorMethod<[string], string>,
  'list_backend_controllers' : ActorMethod<[string], string>,
  'list_governance_requests' : ActorMethod<[string], string>,
  'list_orchestration_actions' : ActorMethod<[], string>,
  'list_permissions' : ActorMethod<[], string>,
  'list_pool' : ActorMethod<[], string>,
  'list_principal_aliases' : ActorMethod<[], string>,
  'list_sections' : ActorMethod<[], string>,
  'list_subnets' : ActorMethod<[], string>,
  'orchestration_configure_baton' : ActorMethod<[string], string>,
  'orchestration_execute_action' : ActorMethod<[string], string>,
  'orchestration_hand_to_baton' : ActorMethod<[string], string>,
  'orchestration_prepare_asset_provision' : ActorMethod<[string], string>,
  'orchestration_prepare_managed_upgrade' : ActorMethod<[string], string>,
  'orchestration_refresh' : ActorMethod<[string], string>,
  'orchestration_status' : ActorMethod<[string], string>,
  'pool_remove' : ActorMethod<[string], string>,
  'provision_assets' : ActorMethod<[string], string>,
  'reconcile' : ActorMethod<[], string>,
  'refresh_canisters' : ActorMethod<[string], string>,
  'refresh_controllers_cache' : ActorMethod<[string], string>,
  'refresh_fx' : ActorMethod<[], string>,
  'refresh_treasury' : ActorMethod<[string], string>,
  'register_canister' : ActorMethod<[string], string>,
  'reject_governance_request' : ActorMethod<[string], string>,
  'remove_authorized_wasm' : ActorMethod<[string], string>,
  'remove_commander' : ActorMethod<[string], string>,
  'rename_canister' : ActorMethod<[string], string>,
  'rename_section' : ActorMethod<[string], string>,
  'rename_stand' : ActorMethod<[string], string>,
  'repair_section' : ActorMethod<[string], string>,
  'reset_sheet' : ActorMethod<[], string>,
  'return_cycles' : ActorMethod<[string], string>,
  'revert_snapshot' : ActorMethod<[string], string>,
  'set_active_arrangement' : ActorMethod<[string], string>,
  'set_arrangement' : ActorMethod<[string], string>,
  'set_canister_controllers' : ActorMethod<[string], string>,
  'set_canister_tags' : ActorMethod<[string], string>,
  'set_commander' : ActorMethod<[string], string>,
  'set_cycle_policy' : ActorMethod<[string], string>,
  'set_log_visibility' : ActorMethod<[string], string>,
  'set_orchestration_policies' : ActorMethod<[string], string>,
  'set_permissions' : ActorMethod<[string], string>,
  'set_principal_alias' : ActorMethod<[string], string>,
  'set_settings' : ActorMethod<[string], string>,
  'set_sheet' : ActorMethod<[string], string>,
  'set_subnet_whitelist' : ActorMethod<[string], string>,
  'start_canister' : ActorMethod<[string], string>,
  'stop_canister' : ActorMethod<[string], string>,
  'sync_controllers' : ActorMethod<[string], string>,
  'top_up' : ActorMethod<[string], string>,
  'upgrade_to' : ActorMethod<[string], string>,
}
export declare const idlFactory: IDL.InterfaceFactory;
export declare const init: (args: { IDL: typeof IDL }) => IDL.Type[];
