import { Badge, type BadgeTone } from '@/components/ui/Badge';
import type { Provenance } from '@/data/localSituationContract';

function sourceDetails(provenance: Provenance): { label: string; tone: BadgeTone } {
  switch (provenance) {
    case 'observed': return { label: 'Наблюдение источника', tone: 'low' };
    case 'derived': return { label: 'Расчёт из источника', tone: 'medium' };
    case 'simulated': return { label: 'Симуляция', tone: 'high' };
    default: return { label: 'Источник недоступен', tone: 'neutral' };
  }
}

export function SourceBadge({ provenance }: { provenance: Provenance }) {
  const source = sourceDetails(provenance);
  return <Badge tone={source.tone}>{source.label}</Badge>;
}
