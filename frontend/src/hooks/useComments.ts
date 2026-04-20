/**
 * React Query hooks for comment CRUD (FR-COMMENT-1..4).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createComment, deleteComment, listComments, updateComment } from "@/api/comments";
import type { CommentCreateBody } from "@/api/comments";

export const COMMENTS_KEY = "comments";

export function useComments() {
  return useQuery({
    queryKey: [COMMENTS_KEY],
    queryFn: listComments,
    staleTime: 30_000,
  });
}

export function useCreateComment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CommentCreateBody) => createComment(body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [COMMENTS_KEY] }),
  });
}

export function useUpdateComment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) => updateComment(id, text),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [COMMENTS_KEY] }),
  });
}

export function useDeleteComment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteComment(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [COMMENTS_KEY] }),
  });
}
