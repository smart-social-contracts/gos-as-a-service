export const idlFactory = ({ IDL }) => {
  const JobStatusAck = IDL.Record({
    'status' : IDL.Text,
    'prev_status' : IDL.Text,
    'noop' : IDL.Bool,
    'job_id' : IDL.Text,
  });
  const InstallerError = IDL.Record({
    'message' : IDL.Text,
    'traceback' : IDL.Text,
  });
  const ResultJobCancel = IDL.Variant({
    'Ok' : JobStatusAck,
    'Err' : InstallerError,
  });
  const EnqueueOk = IDL.Record({
    'status' : IDL.Text,
    'network' : IDL.Text,
    'job_id' : IDL.Text,
    'realm_name' : IDL.Text,
  });
  const ResultEnqueue = IDL.Variant({
    'Ok' : EnqueueOk,
    'Err' : InstallerError,
  });
  const PublicLogEntry = IDL.Record({
    'id' : IDL.Nat,
    'level' : IDL.Text,
    'logger_name' : IDL.Text,
    'message' : IDL.Text,
    'timestamp' : IDL.Nat,
  });
  const CasalsConfigView = IDL.Record({
    'create_stand_baton' : IDL.Bool,
    'provision_via_casals' : IDL.Bool,
    'casals_section' : IDL.Text,
    'registry_principal' : IDL.Text,
    'casals_canister_id' : IDL.Text,
    'baton_wasm_key' : IDL.Text,
  });
  const ResultCasalsConfig = IDL.Variant({
    'Ok' : CasalsConfigView,
    'Err' : InstallerError,
  });
  const DeployStepView = IDL.Record({
    'idx' : IDL.Nat32,
    'status' : IDL.Text,
    'kind' : IDL.Text,
    'label' : IDL.Text,
    'error' : IDL.Text,
  });
  const DeployTaskView = IDL.Record({
    'status' : IDL.Text,
    'task_id' : IDL.Text,
    'completed_count' : IDL.Nat32,
    'steps' : IDL.Vec(DeployStepView),
    'total_count' : IDL.Nat32,
  });
  const ResultDeployTaskStatus = IDL.Variant({
    'Ok' : DeployTaskView,
    'Err' : InstallerError,
  });
  const DeploymentJobView = IDL.Record({
    'status' : IDL.Text,
    'expected_wasm_hash' : IDL.Text,
    'registry_canister_id' : IDL.Text,
    'backend_canister_id' : IDL.Text,
    'ext_deploy_task_id' : IDL.Text,
    'assets_verified' : IDL.Int8,
    'expected_step_count' : IDL.Nat32,
    'network' : IDL.Text,
    'frontend_wasm_verified' : IDL.Int8,
    'created_at' : IDL.Nat64,
    'error' : IDL.Text,
    'wasm_verified' : IDL.Int8,
    'job_id' : IDL.Text,
    'realm_name' : IDL.Text,
    'actual_wasm_hash' : IDL.Text,
    'caller_principal' : IDL.Text,
    'completed_at' : IDL.Nat64,
    'frontend_canister_id' : IDL.Text,
  });
  const ResultJobIdStatus = IDL.Variant({
    'Ok' : DeploymentJobView,
    'Err' : InstallerError,
  });
  const ResultJobManifest = IDL.Variant({
    'Ok' : IDL.Text,
    'Err' : InstallerError,
  });
  const PendingJobEntry = IDL.Record({
    'job' : DeploymentJobView,
    'manifest' : IDL.Text,
  });
  const PendingJobsOk = IDL.Record({
    'jobs' : IDL.Vec(PendingJobEntry),
    'count' : IDL.Nat32,
  });
  const ResultPendingJobs = IDL.Variant({
    'Ok' : PendingJobsOk,
    'Err' : InstallerError,
  });
  const HealthView = IDL.Record({ 'ok' : IDL.Bool, 'canister' : IDL.Text });
  const JobsListOk = IDL.Record({
    'jobs' : IDL.Vec(DeploymentJobView),
    'count' : IDL.Nat32,
  });
  const ResultJobsList = IDL.Variant({
    'Ok' : JobsListOk,
    'Err' : InstallerError,
  });
  const ProvisionOk = IDL.Record({
    'status' : IDL.Text,
    'backend_canister_id' : IDL.Text,
    'stand' : IDL.Text,
    'job_id' : IDL.Text,
    'frontend_canister_id' : IDL.Text,
  });
  const ResultProvision = IDL.Variant({
    'Ok' : ProvisionOk,
    'Err' : InstallerError,
  });
  const ReportReadyOk = IDL.Record({
    'status' : IDL.Text,
    'expected_wasm_hash' : IDL.Text,
    'failed_verification' : IDL.Bool,
    'extensions_started' : IDL.Bool,
    'wasm_verified' : IDL.Bool,
    'job_id' : IDL.Text,
    'actual_wasm_hash' : IDL.Text,
  });
  const ResultReportReady = IDL.Variant({
    'Ok' : ReportReadyOk,
    'Err' : InstallerError,
  });
  const ResultReportFailure = IDL.Variant({
    'Ok' : JobStatusAck,
    'Err' : InstallerError,
  });
  const ReportFrontendOk = IDL.Record({
    'status' : IDL.Text,
    'assets_verified' : IDL.Int8,
    'failed_verification' : IDL.Bool,
    'frontend_wasm_verified' : IDL.Bool,
    'job_id' : IDL.Text,
    'actual_assets_hash' : IDL.Text,
    'actual_frontend_wasm_hash' : IDL.Text,
  });
  const ResultReportFrontend = IDL.Variant({
    'Ok' : ReportFrontendOk,
    'Err' : InstallerError,
  });
  const StatusRecord = IDL.Record({
    'status' : IDL.Text,
    'version' : IDL.Text,
    'commit' : IDL.Text,
    'commit_datetime' : IDL.Text,
  });
  const GetStatusResult = IDL.Variant({
    'Ok' : StatusRecord,
    'Err' : IDL.Text,
  });
  const TakeSnapshotOk = IDL.Record({
    'skipped' : IDL.Bool,
    'job_id' : IDL.Text,
    'snapshot_id' : IDL.Text,
  });
  const ResultTakeSnapshot = IDL.Variant({
    'Ok' : TakeSnapshotOk,
    'Err' : InstallerError,
  });
  return IDL.Service({
    '__get_candid_interface_tmp_hack' : IDL.Func([], [IDL.Text], ['query']),
    'backfill_job_refs_batch' : IDL.Func([], [IDL.Text], []),
    'cancel_deployment' : IDL.Func([IDL.Text], [ResultJobCancel], []),
    'delete_deployment_job' : IDL.Func([IDL.Text], [ResultJobCancel], []),
    'destroy_realm_job' : IDL.Func([IDL.Text], [ResultJobCancel], []),
    'enqueue_deployment' : IDL.Func([IDL.Text], [ResultEnqueue], []),
    'get_canister_logs' : IDL.Func(
        [
          IDL.Opt(IDL.Nat),
          IDL.Opt(IDL.Nat),
          IDL.Opt(IDL.Text),
          IDL.Opt(IDL.Text),
        ],
        [IDL.Vec(PublicLogEntry)],
        ['query'],
      ),
    'get_casals_config' : IDL.Func([], [ResultCasalsConfig], ['query']),
    'get_deploy_task_status' : IDL.Func(
        [IDL.Text],
        [ResultDeployTaskStatus],
        ['query'],
      ),
    'get_deployment_job_status' : IDL.Func(
        [IDL.Text],
        [ResultJobIdStatus],
        ['query'],
      ),
    'get_deployment_manifest' : IDL.Func(
        [IDL.Text],
        [ResultJobManifest],
        ['query'],
      ),
    'get_pending_deployments' : IDL.Func([], [ResultPendingJobs], ['query']),
    'health' : IDL.Func([], [HealthView], ['query']),
    'list_deployment_jobs' : IDL.Func(
        [IDL.Opt(IDL.Nat32), IDL.Opt(IDL.Nat32)],
        [ResultJobsList],
        ['query'],
      ),
    'provision_quarter' : IDL.Func([IDL.Text], [IDL.Text], []),
    'provision_via_casals' : IDL.Func([IDL.Text], [ResultProvision], []),
    'retry_deployment' : IDL.Func([IDL.Text], [ResultProvision], []),
    'report_canister_ready' : IDL.Func([IDL.Text], [ResultReportReady], []),
    'report_deployment_failure' : IDL.Func(
        [IDL.Text],
        [ResultReportFailure],
        [],
      ),
    'report_frontend_verified' : IDL.Func(
        [IDL.Text],
        [ResultReportFrontend],
        [],
      ),
    'set_casals_config' : IDL.Func([IDL.Text], [ResultCasalsConfig], []),
    'status' : IDL.Func([], [GetStatusResult], ['query']),
    'take_pre_upgrade_snapshot' : IDL.Func(
        [IDL.Text],
        [ResultTakeSnapshot],
        [],
      ),
  });
};
export const init = ({ IDL }) => { return []; };
