'use client';

import { PageHeader } from './PageHeader';
import { UnavailableCapability } from './LocalSituationState';

export function CapabilityUnavailablePage({
  eyebrow,
  title,
  description,
  unavailableDescription,
}: {
  eyebrow: string;
  title: string;
  description: string;
  unavailableDescription: string;
}) {
  return <><PageHeader eyebrow={eyebrow} title={title} description={description} /><UnavailableCapability title={title} description={unavailableDescription} /></>;
}
