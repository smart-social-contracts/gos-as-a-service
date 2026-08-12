export const idlFactory = ({ IDL }) => {
  return IDL.Service({
    'list_subnets' : IDL.Func([], [IDL.Text], []),
  });
};
