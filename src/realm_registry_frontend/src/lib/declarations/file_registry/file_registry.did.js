export const idlFactory = ({ IDL }) => {
  const Header = IDL.Tuple(IDL.Text, IDL.Text);
  const HttpRequest = IDL.Record({
    'url' : IDL.Text,
    'method' : IDL.Text,
    'body' : IDL.Vec(IDL.Nat8),
    'headers' : IDL.Vec(Header),
  });
  const HttpResponseIncoming = IDL.Record({
    'body' : IDL.Vec(IDL.Nat8),
    'headers' : IDL.Vec(Header),
    'upgrade' : IDL.Opt(IDL.Bool),
    'streaming_strategy' : IDL.Opt(IDL.Text),
    'status_code' : IDL.Nat16,
  });
  return IDL.Service({
    '__get_candid_interface_tmp_hack' : IDL.Func([], [IDL.Text], ['query']),
    'delete_file' : IDL.Func([IDL.Text], [IDL.Text], []),
    'delete_namespace' : IDL.Func([IDL.Text], [IDL.Text], []),
    'finalize_chunked_file' : IDL.Func([IDL.Text], [IDL.Text], []),
    'finalize_chunked_file_step' : IDL.Func([IDL.Text], [IDL.Text], []),
    'get_acl' : IDL.Func([], [IDL.Text], ['query']),
    'get_backend_files' : IDL.Func([IDL.Text], [IDL.Text], ['query']),
    'get_backend_files_icc' : IDL.Func(
        [IDL.Text, IDL.Text, IDL.Text],
        [IDL.Text],
        ['query'],
      ),
    'get_extension_manifest' : IDL.Func([IDL.Text], [IDL.Text], ['query']),
    'get_file' : IDL.Func([IDL.Text], [IDL.Text], ['query']),
    'get_file_chunk' : IDL.Func([IDL.Text], [IDL.Text], ['query']),
    'get_file_chunk_icc' : IDL.Func(
        [IDL.Text, IDL.Text, IDL.Text, IDL.Text],
        [IDL.Text],
        ['query'],
      ),
    'get_file_size' : IDL.Func([IDL.Text], [IDL.Text], ['query']),
    'get_file_size_icc' : IDL.Func([IDL.Text, IDL.Text], [IDL.Text], ['query']),
    'get_frontend_files' : IDL.Func([IDL.Text], [IDL.Text], ['query']),
    'get_frontend_files_icc' : IDL.Func(
        [IDL.Text, IDL.Text],
        [IDL.Text],
        ['query'],
      ),
    'get_stats' : IDL.Func([], [IDL.Text], ['query']),
    'grant_publish' : IDL.Func([IDL.Text], [IDL.Text], []),
    'http_request' : IDL.Func([HttpRequest], [HttpResponseIncoming], ['query']),
    'http_request_update' : IDL.Func([HttpRequest], [HttpResponseIncoming], []),
    'latest_version' : IDL.Func([IDL.Text], [IDL.Text], ['query']),
    'list_codices' : IDL.Func([], [IDL.Text], ['query']),
    'list_extensions' : IDL.Func([], [IDL.Text], ['query']),
    'list_files' : IDL.Func([IDL.Text], [IDL.Text], ['query']),
    'list_namespaces' : IDL.Func([], [IDL.Text], ['query']),
    'publish_namespace' : IDL.Func([IDL.Text], [IDL.Text], []),
    'purge_old_versions' : IDL.Func([IDL.Text], [IDL.Text], []),
    'revoke_publish' : IDL.Func([IDL.Text], [IDL.Text], []),
    'store_file' : IDL.Func([IDL.Text], [IDL.Text], []),
    'store_file_chunk' : IDL.Func([IDL.Text], [IDL.Text], []),
    'update_namespace' : IDL.Func([IDL.Text], [IDL.Text], []),
  });
};
export const init = ({ IDL }) => { return []; };
