// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { getFastSubmissionChecks, getReviewerDocumentIssues } from './verify-submission-fast.mjs';

describe('getFastSubmissionChecks', () => {
  it('uses only short static checks required before submission', () => {
    expect(getFastSubmissionChecks('python')).toEqual([
      { command: 'node', args: ['scripts/pre-commit-guard.mjs'] },
      { command: 'node', args: ['scripts/pre-commit-guard.mjs', '--tracked'] },
      { command: 'npm', args: ['run', 'typecheck'] },
      { command: 'npm', args: ['run', 'lint'] },
      { command: 'python', args: ['-m', 'ruff', 'check', '.'] },
      { command: 'git', args: ['diff', '--check'] },
    ]);
  });
});

describe('getReviewerDocumentIssues', () => {
  it('requires reviewer entry points and rejects obsolete current-release wording', () => {
    expect(getReviewerDocumentIssues({
      'README.md': '# ФОРПОСТ\nrelease v10\n',
      'START_HERE.md': '# START HERE\n',
      'LTC_2026_SUBMISSION.md': '# LTC 2026\n',
      'docs/TZ_COMPLIANCE.md': '# ТЗ\n',
      'docs/ML_METHODS.md': 'v10\n',
      'docs/ML_CAPABILITIES.md': 'v10\n',
      'docs/DATA_CARD.md': '# Data Card\n',
      'docs/PERFORMANCE.md': '# Performance\n',
      'docs/SECURITY_AUDIT.md': '# Security\n',
      'docs/TEST_PROTOCOL.md': '# Test protocol\n',
    })).toEqual([]);

    expect(getReviewerDocumentIssues({
      'README.md': '# ФОРПОСТ\nТекущий release v9\n',
    })).toEqual([
      'Отсутствует обязательный reviewer-файл: START_HERE.md',
      'Отсутствует обязательный reviewer-файл: LTC_2026_SUBMISSION.md',
      'Отсутствует обязательный reviewer-файл: docs/TZ_COMPLIANCE.md',
      'Отсутствует обязательный reviewer-файл: docs/ML_METHODS.md',
      'Отсутствует обязательный reviewer-файл: docs/ML_CAPABILITIES.md',
      'Отсутствует обязательный reviewer-файл: docs/DATA_CARD.md',
      'Отсутствует обязательный reviewer-файл: docs/PERFORMANCE.md',
      'Отсутствует обязательный reviewer-файл: docs/SECURITY_AUDIT.md',
      'Отсутствует обязательный reviewer-файл: docs/TEST_PROTOCOL.md',
      'README.md содержит устаревшее current-release упоминание v9.',
    ]);
  });
});
