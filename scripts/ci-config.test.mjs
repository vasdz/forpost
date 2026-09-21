// @vitest-environment node
import { readFileSync } from 'node:fs';

import yaml from 'js-yaml';
import { describe, expect, it } from 'vitest';

function loadWorkflow() {
  const document = yaml.load(readFileSync('.github/workflows/ci.yml', 'utf8'));
  const triggers = document.on ?? document.true;
  return { document, triggers };
}

describe('CI perimeter gate', () => {
  it('runs the perimeter job for every push and pull request', () => {
    const { triggers } = loadWorkflow();

    expect(triggers.push).toEqual({});
    expect(triggers.pull_request).toEqual({});
  });

  it('runs the repository guard before any dependency installation in its job', () => {
    const { document } = loadWorkflow();
    const stepNames = document.jobs['perimeter-guard'].steps.map((step) => step.name);

    expect(stepNames.indexOf('Block committed data and oversized files')).toBeGreaterThan(-1);
    expect(stepNames.indexOf('Install frontend dependencies')).toBe(-1);
  });

  it('waits for the perimeter guard before starting every other job', () => {
    const { document } = loadWorkflow();
    const jobsWithoutGuard = Object.entries(document.jobs)
      .filter(([jobName]) => jobName !== 'perimeter-guard')
      .map(([, job]) => job);

    expect(jobsWithoutGuard).not.toHaveLength(0);
    jobsWithoutGuard.forEach((job) => {
      expect(job.needs).toBe('perimeter-guard');
    });
  });

  it('audits the hash-pinned production dependency graph', () => {
    const { document } = loadWorkflow();
    const auditStep = document.jobs['dependency-audit'].steps.find(
      (step) => step.name === 'Audit Python dependencies',
    );

    expect(auditStep.run).toContain('pip-audit --disable-pip -r requirements-prod.lock');
    expect(auditStep.run).not.toContain('--skip-editable');
  });
});
