import { useMutation } from '@tanstack/react-query'
import type { ReviewRequest, ReviewResult } from '../types/review'
import request from '../utils/request'

export function useReview() {
  return useMutation({
    mutationFn: async (params: ReviewRequest) => {
      const response = await request.post<{ code: string; data: ReviewResult }>('/review', params)
      return response.data.data
    },
  })
}
