import type { Principal } from '@dfinity/principal';
import type { ActorMethod } from '@dfinity/agent';
import type { IDL } from '@dfinity/candid';

export interface Account {
  'owner' : Principal,
  'subaccount' : [] | [Uint8Array | number[]],
}
export interface AccountBalanceArgs { 'account' : Uint8Array | number[] }
export type AccountIdentifier = Uint8Array | number[];
export interface AccountTransaction {
  'id' : bigint,
  'transaction' : Transaction,
}
export type AddCreditsResult = { 'Ok' : UserCreditsRecord } |
  { 'Err' : string };
export type AddRealmResult = { 'Ok' : string } |
  { 'Err' : string };
export type Address = string;
export interface Approve {
  'fee' : [] | [bigint],
  'from' : Account,
  'memo' : [] | [Array<bigint>],
  'created_at_time' : [] | [bigint],
  'amount' : bigint,
  'expected_allowance' : [] | [bigint],
  'expires_at' : [] | [bigint],
  'spender' : Spender,
}
export interface Archive { 'canister_id' : Principal }
export interface Archives { 'archives' : Array<Archive> }
export interface Asset { 'class' : AssetClass, 'symbol' : string }
export interface AssetCanisterService {
  'store' : ActorMethod<[_AssetStoreArg], undefined>,
}
export type AssetClass = { 'Cryptocurrency' : null } |
  { 'FiatCurrency' : null };
export interface AssistantInput {
  'categories' : string,
  'eval_report_url' : string,
  'training_data_summary' : string,
  'requested_role' : string,
  'icon' : string,
  'name' : string,
  'requested_permissions' : string,
  'languages' : string,
  'description' : string,
  'version' : string,
  'endpoint_url' : string,
  'domains' : string,
  'assistant_id' : string,
  'base_model' : string,
  'file_registry_canister_id' : string,
  'price_e8s' : bigint,
  'runtime' : string,
  'file_registry_namespace' : string,
  'pricing_summary' : string,
}
export interface AssistantListResult {
  'per_page' : bigint,
  'listings' : Array<AssistantListing>,
  'page' : bigint,
  'total_count' : bigint,
}
export interface AssistantListing {
  'categories' : string,
  'eval_report_url' : string,
  'training_data_summary' : string,
  'requested_role' : string,
  'updated_at' : number,
  'icon' : string,
  'name' : string,
  'verification_notes' : string,
  'requested_permissions' : string,
  'languages' : string,
  'installs' : bigint,
  'description' : string,
  'created_at' : number,
  'verification_status' : string,
  'likes' : bigint,
  'version' : string,
  'endpoint_url' : string,
  'domains' : string,
  'assistant_id' : string,
  'base_model' : string,
  'assistant_alias' : string,
  'is_active' : boolean,
  'file_registry_canister_id' : string,
  'price_e8s' : bigint,
  'runtime' : string,
  'file_registry_namespace' : string,
  'developer' : string,
  'pricing_summary' : string,
}
export type AssistantResult = { 'Ok' : AssistantListing } |
  { 'Err' : string };
export type AuthorityError = { 'GenericError' : GenericError } |
  { 'NonExistingTokenId' : null } |
  { 'Unauthorized' : null } |
  { 'InvalidRecipient' : null };
export type AuthorityResult = { 'Ok' : bigint } |
  { 'Err' : AuthorityError };
export interface BadBurn { 'min_burn_amount' : bigint }
export interface BadFee { 'expected_fee' : bigint }
export interface BillingStatusRecord {
  'total_spent' : bigint,
  'total_balance' : bigint,
  'total_purchased' : bigint,
  'users_count' : bigint,
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
export interface BurnTx {
  'from' : Account,
  'memo' : [] | [Array<bigint>],
  'created_at_time' : [] | [bigint],
  'amount' : bigint,
  'spender' : [] | [Spender],
}
export type Callback = ActorMethod<
  [StreamingToken],
  StreamingCallbackHttpResponse
>;
export interface CallbackStrategy {
  'token' : StreamingToken,
  'callback' : Callback,
}
export interface CanisterInfo {
  'canister_id' : string,
  'canister_type' : string,
}
export interface CanisterSettings {
  'freezing_threshold' : [] | [bigint],
  'controllers' : [] | [Array<Principal>],
  'memory_allocation' : [] | [bigint],
  'compute_allocation' : [] | [bigint],
}
export interface CanisterSnapshotResult {
  'id' : Uint8Array | number[],
  'total_size' : bigint,
  'taken_at_timestamp' : bigint,
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
export interface CapitalPopulationService {
  'report_quarter_population' : ActorMethod<[bigint], string>,
}
export interface CasalsConfigView {
  'create_stand_baton' : boolean,
  'provision_via_casals' : boolean,
  'casals_section' : string,
  'registry_principal' : string,
  'casals_canister_id' : string,
  'baton_wasm_key' : string,
}
export interface CasalsProvisionService {
  'create_canister' : ActorMethod<[string], string>,
}
export interface CasalsService {
  'create_canister' : ActorMethod<[string], string>,
  'create_stand' : ActorMethod<[string], string>,
  'destroy_stand' : ActorMethod<[string], string>,
  'get_tree' : ActorMethod<[], string>,
  'orchestration_configure_baton' : ActorMethod<[string], string>,
  'orchestration_hand_to_baton' : ActorMethod<[string], string>,
  'set_commander' : ActorMethod<[string], string>,
  'upgrade_to' : ActorMethod<[string], string>,
}
export interface ChunkHash { 'hash' : Uint8Array | number[] }
export interface ClearChunkStoreArgs { 'canister_id' : Principal }
export interface CodexInput {
  'categories' : string,
  'icon' : string,
  'name' : string,
  'description' : string,
  'version' : string,
  'codex_id' : string,
  'realm_type' : string,
  'file_registry_canister_id' : string,
  'price_e8s' : bigint,
  'file_registry_namespace' : string,
}
export interface CodexListResult {
  'per_page' : bigint,
  'listings' : Array<CodexListing>,
  'page' : bigint,
  'total_count' : bigint,
}
export interface CodexListing {
  'categories' : string,
  'updated_at' : number,
  'icon' : string,
  'name' : string,
  'verification_notes' : string,
  'installs' : bigint,
  'description' : string,
  'created_at' : number,
  'verification_status' : string,
  'likes' : bigint,
  'version' : string,
  'codex_id' : string,
  'realm_type' : string,
  'is_active' : boolean,
  'file_registry_canister_id' : string,
  'codex_alias' : string,
  'price_e8s' : bigint,
  'file_registry_namespace' : string,
  'developer' : string,
}
export type CodexResult = { 'Ok' : CodexListing } |
  { 'Err' : string };
export interface ConfigRecord {
  'billing_service_principal' : string,
  'license_price_usd_cents' : bigint,
  'license_duration_seconds' : bigint,
  'file_registry_canister_id' : string,
}
export type ConfigResult = { 'Ok' : ConfigRecord } |
  { 'Err' : string };
export interface CreateCanisterArgs { 'settings' : [] | [CanisterSettings] }
export interface CreateCanisterResult { 'canister_id' : Principal }
export interface CreditTransactionRecord {
  'id' : string,
  'transaction_type' : string,
  'description' : string,
  'timestamp' : number,
  'stripe_session_id' : string,
  'principal_id' : string,
  'amount' : bigint,
}
export interface CryptoResponse {
  'data' : CryptoResponseData,
  'success' : boolean,
}
export type CryptoResponseData = { 'scopeList' : ScopeListRecord } |
  { 'envelope' : EnvelopeRecord } |
  { 'error' : string } |
  { 'envelopeList' : EnvelopeListRecord } |
  { 'groupMembers' : GroupMembersRecord } |
  { 'group' : GroupRecord } |
  { 'message' : string } |
  { 'groupList' : GroupListRecord };
export interface DecimalsResult { 'decimals' : number }
export type DeductCreditsResult = { 'Ok' : UserCreditsRecord } |
  { 'Err' : string };
export interface DefiniteCanisterSettings {
  'freezing_threshold' : bigint,
  'controllers' : Array<Principal>,
  'memory_allocation' : bigint,
  'compute_allocation' : bigint,
}
export interface DeleteCanisterArgs { 'canister_id' : Principal }
export interface DeleteCanisterSnapshotArgs {
  'canister_id' : Principal,
  'snapshot_id' : Uint8Array | number[],
}
export interface DemoRegistrationService {
  'register_demo_citizens' : ActorMethod<[string], string>,
}
export interface DeployStepView {
  'idx' : number,
  'status' : string,
  'kind' : string,
  'label' : string,
  'error' : string,
}
export interface DeployTaskView {
  'status' : string,
  'task_id' : string,
  'completed_count' : number,
  'steps' : Array<DeployStepView>,
  'total_count' : number,
}
export interface DeploymentJobView {
  'status' : string,
  'expected_wasm_hash' : string,
  'registry_canister_id' : string,
  'backend_canister_id' : string,
  'ext_deploy_task_id' : string,
  'assets_verified' : number,
  'expected_step_count' : number,
  'network' : string,
  'frontend_wasm_verified' : number,
  'created_at' : bigint,
  'error' : string,
  'wasm_verified' : number,
  'job_id' : string,
  'realm_name' : string,
  'actual_wasm_hash' : string,
  'caller_principal' : string,
  'completed_at' : bigint,
  'frontend_canister_id' : string,
}
export interface DepositCyclesArgs { 'canister_id' : Principal }
export interface DeveloperLicense {
  'last_payment_amount_usd_cents' : bigint,
  'principal' : string,
  'note' : string,
  'last_payment_id' : string,
  'created_at' : number,
  'payment_method' : string,
  'is_active' : boolean,
  'expires_at' : number,
}
export interface Duplicate { 'duplicate_of' : bigint }
export type Duration = bigint;
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
export interface EnqueueOk {
  'status' : string,
  'network' : string,
  'job_id' : string,
  'realm_name' : string,
}
export interface EnvelopeListRecord { 'envelopes' : Array<EnvelopeRecord> }
export interface EnvelopeRecord {
  'scope' : string,
  'principal_id' : string,
  'wrapped_dek' : string,
}
export interface ExchangeRate {
  'metadata' : ExchangeRateMetadata,
  'rate' : bigint,
  'timestamp' : bigint,
  'quote_asset' : Asset,
  'base_asset' : Asset,
}
export type ExchangeRateError = { 'AnonymousPrincipalNotAllowed' : null } |
  { 'CryptoQuoteAssetNotFound' : null } |
  { 'FailedToAcceptCycles' : null } |
  { 'ForexBaseAssetNotFound' : null } |
  { 'CryptoBaseAssetNotFound' : null } |
  { 'StablecoinRateTooFewRates' : null } |
  { 'ForexAssetsNotFound' : null } |
  { 'InconsistentRatesReceived' : null } |
  { 'RateLimited' : null } |
  { 'StablecoinRateZeroRate' : null } |
  { 'Other' : OtherError } |
  { 'ForexInvalidTimestamp' : null } |
  { 'NotEnoughCycles' : null } |
  { 'ForexQuoteAssetNotFound' : null } |
  { 'StablecoinRateNotFound' : null } |
  { 'Pending' : null };
export interface ExchangeRateMetadata {
  'decimals' : number,
  'forex_timestamp' : [] | [bigint],
  'quote_asset_num_received_rates' : bigint,
  'base_asset_num_received_rates' : bigint,
  'base_asset_num_queried_sources' : bigint,
  'standard_deviation' : bigint,
  'quote_asset_num_queried_sources' : bigint,
}
export interface ExtensionCallArgs {
  'args' : string,
  'function_name' : string,
  'extension_name' : string,
}
export interface ExtensionCallResponse {
  'response' : string,
  'success' : boolean,
}
export interface ExtensionInput {
  'categories' : string,
  'extension_id' : string,
  'icon' : string,
  'name' : string,
  'download_url' : string,
  'description' : string,
  'version' : string,
  'file_registry_canister_id' : string,
  'price_e8s' : bigint,
  'file_registry_namespace' : string,
}
export interface ExtensionListResult {
  'per_page' : bigint,
  'listings' : Array<ExtensionListing>,
  'page' : bigint,
  'total_count' : bigint,
}
export interface ExtensionListing {
  'categories' : string,
  'updated_at' : number,
  'extension_id' : string,
  'icon' : string,
  'name' : string,
  'verification_notes' : string,
  'installs' : bigint,
  'download_url' : string,
  'description' : string,
  'created_at' : number,
  'verification_status' : string,
  'likes' : bigint,
  'version' : string,
  'is_active' : boolean,
  'file_registry_canister_id' : string,
  'price_e8s' : bigint,
  'file_registry_namespace' : string,
  'developer' : string,
}
export type ExtensionResult = { 'Ok' : ExtensionListing } |
  { 'Err' : string };
export interface ExtensionsListRecord { 'extensions' : Array<string> }
export interface FederationService {
  'federation_message' : ActorMethod<[string], string>,
}
export interface FileRegistryService {
  'set_namespace_approval' : ActorMethod<[string], string>,
}
export interface ForceTransferArg {
  'to' : NftAccount,
  'token_id' : bigint,
  'memo' : [] | [string],
}
export interface ForcedTransferArgs {
  'to' : TokenAccount,
  'from' : TokenAccount,
  'memo' : [] | [string],
  'amount' : bigint,
}
export interface FreezeAccountArgs {
  'account' : TokenAccount,
  'reason' : [] | [string],
}
export interface FreezeArg { 'token_id' : bigint, 'reason' : [] | [string] }
export interface GenericError { 'message' : string, 'error_code' : bigint }
export type GenericResult = { 'Ok' : string } |
  { 'Err' : string };
export interface GetAccountTransactionsRequest {
  'max_results' : bigint,
  'start' : [] | [bigint],
  'account' : Account,
}
export interface GetAccountTransactionsResponse {
  'balance' : bigint,
  'transactions' : Array<AccountTransaction>,
  'oldest_tx_id' : [] | [bigint],
}
export interface GetBalanceArgs {
  'network' : BitcoinNetwork,
  'address' : string,
  'min_confirmations' : [] | [number],
}
export type GetBillingStatusResult = { 'Ok' : BillingStatusRecord } |
  { 'Err' : string };
export interface GetBlocksArgs { 'start' : bigint, 'length' : bigint }
export type GetCreditsResult = { 'Ok' : UserCreditsRecord } |
  { 'Err' : string };
export interface GetCurrentFeePercentilesArgs { 'network' : BitcoinNetwork }
export interface GetExchangeRateRequest {
  'timestamp' : [] | [bigint],
  'quote_asset' : Asset,
  'base_asset' : Asset,
}
export type GetExchangeRateResult = { 'Ok' : ExchangeRate } |
  { 'Err' : ExchangeRateError };
export type GetRealmResult = { 'Ok' : RealmRecord } |
  { 'Err' : string };
export type GetStatusResult = { 'Ok' : StatusRecord } |
  { 'Err' : string };
export type GetTransactionsResult = { 'Ok' : GetAccountTransactionsResponse } |
  { 'Err' : string };
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
export interface GroupListRecord { 'groups' : Array<GroupRecord> }
export interface GroupMemberRecord { 'role' : string, 'principal_id' : string }
export interface GroupMembersRecord { 'members' : Array<GroupMemberRecord> }
export interface GroupRecord { 'name' : string, 'description' : string }
export type GuardResult = { 'Ok' : null } |
  { 'Err' : string };
export type Header = [string, string];
export interface HealthView { 'ok' : boolean, 'canister' : string }
export interface HttpHeader { 'value' : string, 'name' : string }
export type HttpMethod = { 'get' : null } |
  { 'head' : null } |
  { 'post' : null };
export interface HttpRequest {
  'url' : string,
  'method' : string,
  'body' : Uint8Array | number[],
  'headers' : Array<Header>,
}
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
export interface HttpResponseIncoming {
  'body' : Uint8Array | number[],
  'headers' : Array<Header>,
  'upgrade' : [] | [boolean],
  'streaming_strategy' : [] | [string],
  'status_code' : number,
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
export interface ICRCIndexer {
  'get_account_transactions' : ActorMethod<
    [GetAccountTransactionsRequest],
    GetTransactionsResult
  >,
}
export interface ICRCLedger {
  'icrc1_balance_of' : ActorMethod<[Account], bigint>,
  'icrc1_fee' : ActorMethod<[], bigint>,
  'icrc1_transfer' : ActorMethod<[TransferArg], TransferResult>,
}
export interface Icrc1MetadataService {
  'icrc1_decimals' : ActorMethod<[], number>,
  'icrc1_name' : ActorMethod<[], string>,
  'icrc1_symbol' : ActorMethod<[], string>,
}
export type InsertError = {
    'ValueTooLarge' : { 'max' : number, 'given' : number }
  } |
  { 'KeyTooLarge' : { 'max' : number, 'given' : number } };
export interface InstallChunkedCodeArgs {
  'arg' : Uint8Array | number[],
  'wasm_module_hash' : Uint8Array | number[],
  'mode' : InstallCodeMode,
  'chunk_hashes_list' : Array<ChunkHash>,
  'target_canister' : Principal,
  'store_canister' : [] | [Principal],
}
export interface InstallCodeArgs {
  'arg' : Uint8Array | number[],
  'wasm_module' : Uint8Array | number[],
  'mode' : InstallCodeMode,
  'canister_id' : Principal,
}
export type InstallCodeMode = { 'reinstall' : null } |
  { 'upgrade' : null } |
  { 'install' : null };
export interface InstallerError { 'message' : string, 'traceback' : string }
export interface InstallerProvisionService {
  'provision_quarter' : ActorMethod<[string], string>,
}
export interface InsufficientFunds { 'balance' : bigint }
export interface JobStatusAck {
  'status' : string,
  'prev_status' : string,
  'noop' : boolean,
  'job_id' : string,
}
export interface JobsListOk {
  'jobs' : Array<DeploymentJobView>,
  'count' : number,
}
export interface KeyId { 'name' : string, 'curve' : EcdsaCurve }
export interface KeyTooLarge { 'max' : number, 'given' : number }
export interface Ledger {
  'account_balance' : ActorMethod<[AccountBalanceArgs], Tokens>,
  'archives' : ActorMethod<[], Archives>,
  'decimals' : ActorMethod<[], DecimalsResult>,
  'name' : ActorMethod<[], NameResult>,
  'query_blocks' : ActorMethod<[GetBlocksArgs], QueryBlocksResponse>,
  'symbol' : ActorMethod<[], SymbolResult>,
  'transfer' : ActorMethod<[TransferArgs], TransferResult>,
  'transfer_fee' : ActorMethod<[TransferFeeArg], TransferFee>,
}
export interface LicensePaymentInput {
  'principal' : string,
  'duration_seconds' : bigint,
  'note' : string,
  'payment_method' : string,
  'stripe_session_id' : string,
  'amount_usd_cents' : bigint,
}
export interface LicensePricingRecord {
  'license_price_usd_cents' : bigint,
  'license_duration_seconds' : bigint,
}
export type LicenseResult = { 'Ok' : DeveloperLicense } |
  { 'Err' : string };
export interface LikeRecord {
  'item_kind' : string,
  'created_at' : number,
  'item_id' : string,
}
export interface ListCanisterSnapshotsArgs { 'canister_id' : Principal }
export interface LoadCanisterSnapshotArgs {
  'canister_id' : Principal,
  'sender_canister_version' : [] | [bigint],
  'snapshot_id' : Uint8Array | number[],
}
export interface ManagementCanister {
  'bitcoin_get_balance' : ActorMethod<[GetBalanceArgs], Satoshi>,
  'bitcoin_get_current_fee_percentiles' : ActorMethod<
    [GetCurrentFeePercentilesArgs],
    BigUint64Array | bigint[]
  >,
  'bitcoin_get_utxos' : ActorMethod<[GetUtxosArgs], GetUtxosResult>,
  'bitcoin_send_transaction' : ActorMethod<[SendTransactionArgs], undefined>,
  'canister_status' : ActorMethod<[CanisterStatusArgs], CanisterStatusResult>,
  'clear_chunk_store' : ActorMethod<[ClearChunkStoreArgs], undefined>,
  'create_canister' : ActorMethod<[CreateCanisterArgs], CreateCanisterResult>,
  'delete_canister' : ActorMethod<[DeleteCanisterArgs], undefined>,
  'delete_canister_snapshot' : ActorMethod<
    [DeleteCanisterSnapshotArgs],
    undefined
  >,
  'deposit_cycles' : ActorMethod<[DepositCyclesArgs], undefined>,
  'ecdsa_public_key' : ActorMethod<[EcdsaPublicKeyArgs], EcdsaPublicKeyResult>,
  'http_request' : ActorMethod<[HttpRequestArgs], HttpResponse>,
  'install_chunked_code' : ActorMethod<[InstallChunkedCodeArgs], undefined>,
  'install_code' : ActorMethod<[InstallCodeArgs], undefined>,
  'list_canister_snapshots' : ActorMethod<
    [ListCanisterSnapshotsArgs],
    Array<CanisterSnapshotResult>
  >,
  'load_canister_snapshot' : ActorMethod<[LoadCanisterSnapshotArgs], undefined>,
  'provisional_create_canister_with_cycles' : ActorMethod<
    [ProvisionalCreateCanisterWithCyclesArgs],
    ProvisionalCreateCanisterWithCyclesResult
  >,
  'provisional_top_up_canister' : ActorMethod<
    [ProvisionalTopUpCanisterArgs],
    undefined
  >,
  'raw_rand' : ActorMethod<[], Uint8Array | number[]>,
  'sign_with_ecdsa' : ActorMethod<[SignWithEcdsaArgs], SignWithEcdsaResult>,
  'start_canister' : ActorMethod<[StartCanisterArgs], undefined>,
  'stop_canister' : ActorMethod<[StopCanisterArgs], undefined>,
  'stored_chunks' : ActorMethod<[StoredChunksArgs], Array<StoredChunksResult>>,
  'take_canister_snapshot' : ActorMethod<
    [TakeCanisterSnapshotArgs],
    CanisterSnapshotResult
  >,
  'uninstall_code' : ActorMethod<[UninstallCodeArgs], undefined>,
  'update_settings' : ActorMethod<[UpdateSettingsArgs], undefined>,
  'upload_chunk' : ActorMethod<[UploadChunkArgs], UploadChunkResult>,
  'vetkd_derive_key' : ActorMethod<[VetKDDeriveKeyArgs], VetKDDeriveKeyResult>,
  'vetkd_public_key' : ActorMethod<[VetKDPublicKeyArgs], VetKDPublicKeyResult>,
}
export interface MarketplaceInitArg {
  'billing_service_principal' : [] | [string],
  'file_registry' : [] | [string],
}
export type Memo = bigint;
export type MetadataValue = { 'Int' : bigint } |
  { 'Nat' : bigint } |
  { 'Blob' : Uint8Array | number[] } |
  { 'Text' : string };
export type MillisatoshiPerByte = bigint;
export interface MintArg {
  'token_id' : [] | [bigint],
  'owner' : NftAccount,
  'metadata' : [] | [Array<[string, MetadataValue]>],
}
export type MintError = { 'GenericError' : GenericError } |
  { 'SupplyCapReached' : null } |
  { 'Unauthorized' : null } |
  { 'TokenIdAlreadyExists' : null };
export type MintResult = { 'Ok' : bigint } |
  { 'Err' : MintError };
export interface MintTx {
  'to' : Account,
  'memo' : [] | [Array<bigint>],
  'created_at_time' : [] | [bigint],
  'amount' : bigint,
}
export interface NFTService {
  'force_transfer' : ActorMethod<[ForceTransferArg], AuthorityResult>,
  'freeze_token' : ActorMethod<[FreezeArg], AuthorityResult>,
  'mint' : ActorMethod<[MintArg], MintResult>,
  'unfreeze_token' : ActorMethod<[bigint], AuthorityResult>,
}
export interface NameResult { 'name' : string }
export interface NftAccount {
  'owner' : Principal,
  'subaccount' : [] | [Uint8Array | number[]],
}
export type NotifyResult = { 'Ok' : null } |
  {
    'Err' : { 'NoError' : null } |
      { 'CanisterError' : null } |
      { 'SysTransient' : null } |
      { 'DestinationInvalid' : null } |
      { 'SysFatal' : null } |
      { 'CanisterReject' : null }
  };
export interface ObjectsListRecord { 'objects' : Array<string> }
export interface ObjectsListRecordPaginated {
  'pagination' : PaginationInfo,
  'objects' : Array<string>,
}
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
export interface OtherError { 'code' : number, 'description' : string }
export interface Outpoint { 'txid' : Uint8Array | number[], 'vout' : number }
export type Page = Uint8Array | number[];
export interface PaginationInfo {
  'page_size' : bigint,
  'total_pages' : bigint,
  'total_items_count' : bigint,
  'page_num' : bigint,
}
export interface PendingAudit {
  'updated_at' : number,
  'name' : string,
  'item_kind' : string,
  'version' : string,
  'item_id' : string,
  'developer' : string,
}
export interface PendingJobEntry {
  'job' : DeploymentJobView,
  'manifest' : string,
}
export interface PendingJobsOk {
  'jobs' : Array<PendingJobEntry>,
  'count' : number,
}
export interface ProvisionOk {
  'status' : string,
  'backend_canister_id' : string,
  'stand' : string,
  'job_id' : string,
  'frontend_canister_id' : string,
}
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
export interface PublicLogEntry {
  'id' : bigint,
  'level' : string,
  'logger_name' : string,
  'message' : string,
  'timestamp' : bigint,
}
export interface PurchaseRecord {
  'purchased_at' : number,
  'item_kind' : string,
  'purchase_id' : string,
  'realm_principal' : string,
  'price_paid_e8s' : bigint,
  'item_id' : string,
  'developer' : string,
}
export interface QuarterBootstrapService {
  'bootstrap_as_quarter' : ActorMethod<[string], string>,
}
export interface QuarterDirectoryService {
  'get_quarter_directory' : ActorMethod<[], string>,
}
export interface QuarterInfoRecord {
  'status' : string,
  'name' : string,
  'canister_id' : string,
  'is_capital' : boolean,
  'index' : bigint,
  'population' : bigint,
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
export interface REnqueueOk {
  'status' : string,
  'network' : string,
  'job_id' : string,
  'realm_name' : string,
}
export interface RInstallerError { 'message' : string, 'traceback' : string }
export interface RProvisionOk {
  'status' : string,
  'backend_canister_id' : string,
  'stand' : string,
  'job_id' : string,
  'frontend_canister_id' : string,
}
export type RResultEnqueue = { 'Ok' : REnqueueOk } |
  { 'Err' : RInstallerError };
export type RResultProvision = { 'Ok' : RProvisionOk } |
  { 'Err' : RInstallerError };
export interface RealmInstallerService {
  'cancel_deployment' : ActorMethod<[string], string>,
  'enqueue_deployment' : ActorMethod<[string], RResultEnqueue>,
  'provision_via_casals' : ActorMethod<[string], RResultProvision>,
}
export interface RealmMessagingService {
  'receive_realm_message' : ActorMethod<
    [string, string, string, string],
    string
  >,
}
export interface RealmRecord {
  'id' : string,
  'url' : string,
  'logo' : string,
  'name' : string,
  'created_at' : number,
  'backend_url' : string,
  'frontend_canister_id' : string,
  'users_count' : bigint,
}
export interface RealmRegistryService {
  'deployment_failed' : ActorMethod<[string, string, string], string>,
  'deployment_succeeded' : ActorMethod<[string, string], string>,
  'register_realm' : ActorMethod<
    [string, string, string, string, string],
    string
  >,
  'remove_realm' : ActorMethod<[string], string>,
}
export interface RealmRegistryUpgradeService {
  'get_credits' : ActorMethod<[string], GetCreditsResult>,
  'get_latest_version' : ActorMethod<[], UpgradeResult>,
  'request_upgrade' : ActorMethod<[string], string>,
}
export interface RealmResponse {
  'data' : RealmResponseData,
  'success' : boolean,
}
export type RealmResponseData = { 'status' : StatusRecord } |
  { 'objectsListPaginated' : ObjectsListRecordPaginated } |
  { 'objectsList' : ObjectsListRecord } |
  { 'extensionsList' : ExtensionsListRecord } |
  { 'userGet' : UserGetRecord } |
  { 'error' : string } |
  { 'message' : string };
export interface RealmTargetService {
  'install_codex_from_registry' : ActorMethod<[string], string>,
  'install_extension_from_registry' : ActorMethod<[string], string>,
}
export type RejectionCode = { 'NoError' : null } |
  { 'CanisterError' : null } |
  { 'SysTransient' : null } |
  { 'DestinationInvalid' : null } |
  { 'SysFatal' : null } |
  { 'CanisterReject' : null };
export interface ReportFrontendOk {
  'status' : string,
  'assets_verified' : number,
  'failed_verification' : boolean,
  'frontend_wasm_verified' : boolean,
  'job_id' : string,
  'actual_assets_hash' : string,
  'actual_frontend_wasm_hash' : string,
}
export interface ReportReadyOk {
  'status' : string,
  'expected_wasm_hash' : string,
  'failed_verification' : boolean,
  'extensions_started' : boolean,
  'wasm_verified' : boolean,
  'job_id' : string,
  'actual_wasm_hash' : string,
}
export type ResultCasalsConfig = { 'Ok' : CasalsConfigView } |
  { 'Err' : InstallerError };
export type ResultDeployTaskStatus = { 'Ok' : DeployTaskView } |
  { 'Err' : InstallerError };
export type ResultEnqueue = { 'Ok' : EnqueueOk } |
  { 'Err' : InstallerError };
export type ResultJobCancel = { 'Ok' : JobStatusAck } |
  { 'Err' : InstallerError };
export type ResultJobIdStatus = { 'Ok' : DeploymentJobView } |
  { 'Err' : InstallerError };
export type ResultJobManifest = { 'Ok' : string } |
  { 'Err' : InstallerError };
export type ResultJobsList = { 'Ok' : JobsListOk } |
  { 'Err' : InstallerError };
export type ResultPendingJobs = { 'Ok' : PendingJobsOk } |
  { 'Err' : InstallerError };
export type ResultProvision = { 'Ok' : ProvisionOk } |
  { 'Err' : InstallerError };
export type ResultReportFailure = { 'Ok' : JobStatusAck } |
  { 'Err' : InstallerError };
export type ResultReportFrontend = { 'Ok' : ReportFrontendOk } |
  { 'Err' : InstallerError };
export type ResultReportReady = { 'Ok' : ReportReadyOk } |
  { 'Err' : InstallerError };
export type ResultTakeSnapshot = { 'Ok' : TakeSnapshotOk } |
  { 'Err' : InstallerError };
export type Satoshi = bigint;
export interface ScopeListRecord { 'scopes' : Array<string> }
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
export interface Spender {
  'owner' : Principal,
  'subaccount' : [] | [Uint8Array | number[]],
}
export type Stable64GrowResult = { 'Ok' : bigint } |
  { 'Err' : { 'OutOfBounds' : null } | { 'OutOfMemory' : null } };
export type StableGrowResult = { 'Ok' : number } |
  { 'Err' : { 'OutOfBounds' : null } | { 'OutOfMemory' : null } };
export type StableMemoryError = { 'OutOfBounds' : null } |
  { 'OutOfMemory' : null };
export interface StartCanisterArgs { 'canister_id' : Principal }
export interface StatusRecord {
  'python_version' : string,
  'status' : string,
  'realms_count' : bigint,
  'version' : string,
  'dependencies' : Array<string>,
  'commit' : string,
  'commit_datetime' : string,
}
export type StatusResult = { 'Ok' : StatusRecord } |
  { 'Err' : string };
export interface StopCanisterArgs { 'canister_id' : Principal }
export interface StoredChunksArgs { 'canister_id' : Principal }
export interface StoredChunksResult { 'hash' : Uint8Array | number[] }
export interface StreamingCallbackHttpResponse {
  'token' : [] | [StreamingToken],
  'body' : Uint8Array | number[],
}
export type StreamingStrategy = { 'Callback' : CallbackStrategy };
export interface StreamingToken { 'key' : string }
export type SubAccount = Uint8Array | number[];
export interface SymbolResult { 'symbol' : string }
export interface TakeCanisterSnapshotArgs {
  'replace_snapshot' : [] | [Uint8Array | number[]],
  'canister_id' : Principal,
}
export interface TakeSnapshotOk {
  'skipped' : boolean,
  'job_id' : string,
  'snapshot_id' : string,
}
export interface TimeStamp { 'timestamp_nanos' : bigint }
export type TimerId = bigint;
export interface TokenAccount {
  'owner' : Principal,
  'subaccount' : [] | [Uint8Array | number[]],
}
export type TokenAuthorityError = { 'GenericError' : string } |
  { 'InsufficientBalance' : null } |
  { 'Unauthorized' : null } |
  { 'InvalidRecipient' : null };
export type TokenAuthorityResult = { 'Ok' : bigint } |
  { 'Err' : TokenAuthorityError };
export interface TokenAuthorityService {
  'forced_transfer' : ActorMethod<[ForcedTransferArgs], TokenAuthorityResult>,
  'freeze_account' : ActorMethod<[FreezeAccountArgs], TokenAuthorityResult>,
  'unfreeze_account' : ActorMethod<[TokenAccount], TokenAuthorityResult>,
}
export interface Tokens { 'e8s' : bigint }
export interface Transaction {
  'memo' : bigint,
  'operation' : [] | [Operation],
  'created_at_time' : TimeStamp,
}
export type TransactionHistoryResult = {
    'Ok' : Array<CreditTransactionRecord>
  } |
  { 'Err' : string };
export interface TransferArg {
  'to' : Account,
  'fee' : [] | [bigint],
  'memo' : [] | [Uint8Array | number[]],
  'from_subaccount' : [] | [Uint8Array | number[]],
  'created_at_time' : [] | [bigint],
  'amount' : bigint,
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
export interface TransferTx {
  'to' : Account,
  'fee' : [] | [bigint],
  'from' : Account,
  'memo' : [] | [Array<bigint>],
  'created_at_time' : [] | [bigint],
  'amount' : bigint,
  'spender' : [] | [Spender],
}
export interface UninstallCodeArgs { 'canister_id' : Principal }
export interface UpdateSettingsArgs {
  'canister_id' : Principal,
  'settings' : CanisterSettings,
}
export type UpgradeResult = { 'Ok' : string } |
  { 'Err' : string };
export interface UploadChunkArgs {
  'chunk' : Uint8Array | number[],
  'canister_id' : Principal,
}
export interface UploadChunkResult { 'hash' : Uint8Array | number[] }
export interface UserCreditsRecord {
  'total_spent' : bigint,
  'balance' : bigint,
  'principal_id' : string,
  'total_purchased' : bigint,
}
export interface UserGetRecord {
  'assigned_quarter' : string,
  'principal' : Principal,
  'private_data' : string,
  'nickname' : string,
  'profiles' : Array<string>,
  'avatar' : string,
}
export interface Utxo {
  'height' : number,
  'value' : bigint,
  'outpoint' : Outpoint,
}
export type UtxosFilter = { 'Page' : Uint8Array | number[] } |
  { 'MinConfirmations' : number };
export interface ValueTooLarge { 'max' : number, 'given' : number }
export interface VersionInfoRecord {
  'backend_wasm_hash' : string,
  'backend_wasm_url' : string,
  'published_at' : number,
  'frontend_tar_url' : string,
  'version' : string,
  'frontend_tar_hash' : string,
}
export type VetKDCurve = { 'bls12_381_g2' : null };
export interface VetKDDeriveKeyArgs {
  'context' : Uint8Array | number[],
  'key_id' : VetKDKeyId,
  'input' : Uint8Array | number[],
  'transport_public_key' : Uint8Array | number[],
}
export interface VetKDDeriveKeyResult {
  'encrypted_key' : Uint8Array | number[],
}
export interface VetKDKeyId { 'name' : string, 'curve' : VetKDCurve }
export interface VetKDPublicKeyArgs {
  'context' : Uint8Array | number[],
  'key_id' : VetKDKeyId,
  'canister_id' : [] | [Principal],
}
export interface VetKDPublicKeyResult { 'public_key' : Uint8Array | number[] }
export interface XRCCanister {
  'get_exchange_rate' : ActorMethod<
    [GetExchangeRateRequest],
    GetExchangeRateResult
  >,
}
export interface _AssetStoreArg {
  'key' : string,
  'content' : Uint8Array | number[],
  'sha256' : [] | [Uint8Array | number[]],
  'content_type' : string,
  'content_encoding' : string,
}
export interface _GetAccountTransactionsArgs {
  'max_results' : bigint,
  'start' : [] | [bigint],
  'account' : _IcrcAccount,
}
export interface _GetAccountTransactionsOk {
  'balance' : bigint,
  'transactions' : Array<_IcrcTransactionWithId>,
}
export type _GetAccountTransactionsResult = {
    'Ok' : _GetAccountTransactionsOk
  } |
  { 'Err' : string };
export interface _ICRC1IndexerService {
  'get_account_transactions' : ActorMethod<
    [_GetAccountTransactionsArgs],
    _GetAccountTransactionsResult
  >,
}
export interface _IcrcAccount {
  'owner' : Principal,
  'subaccount' : [] | [Uint8Array | number[]],
}
export interface _IcrcTransaction {
  'kind' : string,
  'transfer' : [] | [_IcrcTransfer],
}
export interface _IcrcTransactionWithId {
  'id' : bigint,
  'transaction' : _IcrcTransaction,
}
export interface _IcrcTransfer { 'to' : _IcrcAccount, 'amount' : bigint }
export interface _SERVICE {
  '__get_candid_interface_tmp_hack' : ActorMethod<[], string>,
  'add_credits' : ActorMethod<
    [string, bigint, string, string],
    AddCreditsResult
  >,
  'billing_status' : ActorMethod<[], GetBillingStatusResult>,
  'claim_slug' : ActorMethod<
    [string, string, string, string, string],
    GenericResult
  >,
  'create_invitation_codes' : ActorMethod<[string], GenericResult>,
  'deactivate_principal' : ActorMethod<[string], GenericResult>,
  'deduct_credits' : ActorMethod<[string, bigint, string], DeductCreditsResult>,
  'deployment_failed' : ActorMethod<[string, string, string], string>,
  'deployment_succeeded' : ActorMethod<[string, string], string>,
  'get_credits' : ActorMethod<[string], GetCreditsResult>,
  'get_invitation_mode' : ActorMethod<[], GenericResult>,
  'get_latest_version' : ActorMethod<[], UpgradeResult>,
  'get_realm' : ActorMethod<[string], GetRealmResult>,
  'get_runtime_flags' : ActorMethod<[], string>,
  'get_transactions' : ActorMethod<[string, bigint], TransactionHistoryResult>,
  'is_principal_activated' : ActorMethod<[string], GenericResult>,
  'list_activated_principals' : ActorMethod<[], string>,
  'list_invitation_codes' : ActorMethod<[], string>,
  'list_pending_pretty_hostnames' : ActorMethod<[], string>,
  'list_realms' : ActorMethod<[], Array<RealmRecord>>,
  'list_versions' : ActorMethod<[], string>,
  'publish_version' : ActorMethod<[string], UpgradeResult>,
  'realm_count' : ActorMethod<[], bigint>,
  'redeem_invitation_code' : ActorMethod<[string], GenericResult>,
  'register_realm' : ActorMethod<
    [string, string, string, string, string],
    AddRealmResult
  >,
  'remove_realm' : ActorMethod<[string], AddRealmResult>,
  'request_deployment' : ActorMethod<[string], string>,
  'request_upgrade' : ActorMethod<[string], string>,
  'resolve_slug' : ActorMethod<[string], GenericResult>,
  'revoke_invitation_code' : ActorMethod<[string], GenericResult>,
  'set_canister_config_json' : ActorMethod<[string], string>,
  'set_invitation_mode' : ActorMethod<[string], GenericResult>,
  'set_pretty_hostname_status' : ActorMethod<[string, string], GenericResult>,
  'set_test_flags_json' : ActorMethod<[string], string>,
  'status' : ActorMethod<[], GetStatusResult>,
}
export declare const idlFactory: IDL.InterfaceFactory;
export declare const init: (args: { IDL: typeof IDL }) => IDL.Type[];
