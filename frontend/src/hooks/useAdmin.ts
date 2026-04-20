/**
 * React Query hooks for admin API endpoints.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createHubPair,
  createUser,
  deactivateUser,
  deleteHubPair,
  getConfig,
  listHubPairs,
  listUsers,
  updateConfig,
  updateHubPair,
  updateRetention,
  updateUser,
} from "@/api/admin";
import type {
  ConfigUpdateBody,
  HubPairCreateBody,
  HubPairUpdateBody,
  RetentionUpdateBody,
  UserCreateBody,
  UserUpdateBody,
} from "@/api/admin";

export const USERS_KEY = "admin-users";
export const CONFIG_KEY = "admin-config";
export const HUB_PAIRS_KEY = "admin-hub-pairs";

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export function useUsers() {
  return useQuery({ queryKey: [USERS_KEY], queryFn: listUsers });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: UserCreateBody) => createUser(body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [USERS_KEY] }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UserUpdateBody }) => updateUser(id, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [USERS_KEY] }),
  });
}

export function useDeactivateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deactivateUser(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [USERS_KEY] }),
  });
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

export function useConfig() {
  return useQuery({ queryKey: [CONFIG_KEY], queryFn: getConfig });
}

export function useUpdateConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ConfigUpdateBody) => updateConfig(body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [CONFIG_KEY] }),
  });
}

export function useUpdateRetention() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RetentionUpdateBody) => updateRetention(body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [CONFIG_KEY] }),
  });
}

// ---------------------------------------------------------------------------
// Hub pairs
// ---------------------------------------------------------------------------

export function useHubPairs() {
  return useQuery({ queryKey: [HUB_PAIRS_KEY], queryFn: listHubPairs });
}

export function useCreateHubPair() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: HubPairCreateBody) => createHubPair(body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [HUB_PAIRS_KEY] }),
  });
}

export function useUpdateHubPair() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: HubPairUpdateBody }) => updateHubPair(id, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [HUB_PAIRS_KEY] }),
  });
}

export function useDeleteHubPair() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteHubPair(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [HUB_PAIRS_KEY] }),
  });
}
