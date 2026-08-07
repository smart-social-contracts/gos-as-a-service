export const idlFactory = ({ IDL }) => {
  const UserCreditsRecord = IDL.Record({
    'total_spent' : IDL.Nat64,
    'balance' : IDL.Nat64,
    'principal_id' : IDL.Text,
    'total_purchased' : IDL.Nat64,
  });
  const AddCreditsResult = IDL.Variant({
    'Ok' : UserCreditsRecord,
    'Err' : IDL.Text,
  });
  const BillingStatusRecord = IDL.Record({
    'total_spent' : IDL.Nat64,
    'total_balance' : IDL.Nat64,
    'total_purchased' : IDL.Nat64,
    'users_count' : IDL.Nat64,
  });
  const GetBillingStatusResult = IDL.Variant({
    'Ok' : BillingStatusRecord,
    'Err' : IDL.Text,
  });
  const GenericResult = IDL.Variant({ 'Ok' : IDL.Text, 'Err' : IDL.Text });
  const DeductCreditsResult = IDL.Variant({
    'Ok' : UserCreditsRecord,
    'Err' : IDL.Text,
  });
  const GetCreditsResult = IDL.Variant({
    'Ok' : UserCreditsRecord,
    'Err' : IDL.Text,
  });
  const UpgradeResult = IDL.Variant({ 'Ok' : IDL.Text, 'Err' : IDL.Text });
  const RealmRecord = IDL.Record({
    'id' : IDL.Text,
    'url' : IDL.Text,
    'logo' : IDL.Text,
    'name' : IDL.Text,
    'created_at' : IDL.Float64,
    'backend_url' : IDL.Text,
    'frontend_canister_id' : IDL.Text,
    'users_count' : IDL.Nat64,
  });
  const GetRealmResult = IDL.Variant({ 'Ok' : RealmRecord, 'Err' : IDL.Text });
  const CreditTransactionRecord = IDL.Record({
    'id' : IDL.Text,
    'transaction_type' : IDL.Text,
    'description' : IDL.Text,
    'timestamp' : IDL.Float64,
    'stripe_session_id' : IDL.Text,
    'principal_id' : IDL.Text,
    'amount' : IDL.Nat64,
  });
  const TransactionHistoryResult = IDL.Variant({
    'Ok' : IDL.Vec(CreditTransactionRecord),
    'Err' : IDL.Text,
  });
  const AddRealmResult = IDL.Variant({ 'Ok' : IDL.Text, 'Err' : IDL.Text });
  const StatusRecord = IDL.Record({
    'python_version' : IDL.Text,
    'status' : IDL.Text,
    'realms_count' : IDL.Nat64,
    'version' : IDL.Text,
    'dependencies' : IDL.Vec(IDL.Text),
    'commit' : IDL.Text,
    'commit_datetime' : IDL.Text,
  });
  const GetStatusResult = IDL.Variant({
    'Ok' : StatusRecord,
    'Err' : IDL.Text,
  });
  return IDL.Service({
    '__get_candid_interface_tmp_hack' : IDL.Func([], [IDL.Text], ['query']),
    'add_credits' : IDL.Func(
        [IDL.Text, IDL.Nat64, IDL.Text, IDL.Text],
        [AddCreditsResult],
        [],
      ),
    'billing_status' : IDL.Func([], [GetBillingStatusResult], ['query']),
    'claim_slug' : IDL.Func(
        [IDL.Text, IDL.Text, IDL.Text, IDL.Text, IDL.Text],
        [GenericResult],
        [],
      ),
    'create_invitation_codes' : IDL.Func([IDL.Text], [GenericResult], []),
    'deactivate_principal' : IDL.Func([IDL.Text], [GenericResult], []),
    'deduct_credits' : IDL.Func(
        [IDL.Text, IDL.Nat64, IDL.Text],
        [DeductCreditsResult],
        [],
      ),
    'deployment_failed' : IDL.Func(
        [IDL.Text, IDL.Text, IDL.Text],
        [IDL.Text],
        [],
      ),
    'deployment_succeeded' : IDL.Func([IDL.Text, IDL.Text], [IDL.Text], []),
    'get_credits' : IDL.Func([IDL.Text], [GetCreditsResult], ['query']),
    'get_invitation_mode' : IDL.Func([], [GenericResult], ['query']),
    'get_latest_version' : IDL.Func([], [UpgradeResult], ['query']),
    'get_realm' : IDL.Func([IDL.Text], [GetRealmResult], ['query']),
    'get_runtime_flags' : IDL.Func([], [IDL.Text], ['query']),
    'get_transactions' : IDL.Func(
        [IDL.Text, IDL.Nat64],
        [TransactionHistoryResult],
        ['query'],
      ),
    'is_principal_activated' : IDL.Func([IDL.Text], [GenericResult], ['query']),
    'list_activated_principals' : IDL.Func([], [IDL.Text], ['query']),
    'list_invitation_codes' : IDL.Func([], [IDL.Text], ['query']),
    'list_pending_pretty_hostnames' : IDL.Func([], [IDL.Text], ['query']),
    'list_realms' : IDL.Func([], [IDL.Vec(RealmRecord)], ['query']),
    'list_versions' : IDL.Func([], [IDL.Text], ['query']),
    'publish_version' : IDL.Func([IDL.Text], [UpgradeResult], []),
    'realm_count' : IDL.Func([], [IDL.Nat64], ['query']),
    'redeem_invitation_code' : IDL.Func([IDL.Text], [GenericResult], []),
    'register_realm' : IDL.Func(
        [IDL.Text, IDL.Text, IDL.Text, IDL.Text, IDL.Text],
        [AddRealmResult],
        [],
      ),
    'remove_realm' : IDL.Func([IDL.Text], [AddRealmResult], []),
    'request_deployment' : IDL.Func([IDL.Text], [IDL.Text], []),
    'request_upgrade' : IDL.Func([IDL.Text], [IDL.Text], []),
    'resolve_slug' : IDL.Func([IDL.Text], [GenericResult], []),
    'revoke_invitation_code' : IDL.Func([IDL.Text], [GenericResult], []),
    'set_canister_config_json' : IDL.Func([IDL.Text], [IDL.Text], []),
    'set_invitation_mode' : IDL.Func([IDL.Text], [GenericResult], []),
    'set_pretty_hostname_status' : IDL.Func(
        [IDL.Text, IDL.Text],
        [GenericResult],
        [],
      ),
    'set_test_flags_json' : IDL.Func([IDL.Text], [IDL.Text], []),
    'status' : IDL.Func([], [GetStatusResult], ['query']),
  });
};
export const init = ({ IDL }) => { return []; };
