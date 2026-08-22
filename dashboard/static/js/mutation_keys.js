export function createMutationKeyStore(generateKey) {
  const pending = new Map();
  return {
    keyFor(signature, prefix) {
      const key = pending.get(signature) || generateKey(prefix);
      pending.set(signature, key);
      return key;
    },
    complete(signature) {
      pending.delete(signature);
    },
    failed(signature, httpStatus) {
      if (httpStatus && httpStatus < 500) pending.delete(signature);
    }
  };
}
