import { http, HttpResponse } from 'msw'
import type { ReviewResult } from '../types/review'

const mockReview: ReviewResult = {
  pr_url: 'https://github.com/owner/repo/pull/1',
  summary: 'This PR adds authentication middleware. Overall risk is medium.',
  risk_level: 'MEDIUM',
  issues: [
    {
      severity: 'ERROR',
      file: 'src/auth/middleware.ts',
      line: 42,
      title: 'Potential null dereference',
      description: 'user.token may be undefined when session expires',
      suggestion: 'Add null check before accessing user.token',
    },
  ],
  stats: {
    files_changed: 3,
    additions: 120,
    deletions: 45,
    issues_by_severity: { ERROR: 1, WARNING: 2, INFO: 3 },
  },
}

export const handlers = [
  http.post('/api/review', () => {
    return HttpResponse.json({ code: '0', message: 'ok', data: mockReview })
  }),
]
