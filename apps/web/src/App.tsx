import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

import { SecurityProvider, useSecurityContext } from './contexts';
import { Layout } from './layout/Layout';
import { RiskOverview } from './features/risks/RiskOverview';
import { RiskMatrixTable } from './features/risks/RiskMatrixTable';
import { DataIngestHub } from './features/risks/DataIngestHub';
import { AuditConsole } from './features/risks/AuditConsole';
import { MaintenanceHub } from './features/risks/MaintenanceHub';
import { useRisksQuery } from './api/queries';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

function RiskOverviewWrapper() {
  const { context } = useSecurityContext();
  const { data: risks = [] } = useRisksQuery(context);
  return <RiskOverview risks={risks} />;
}

function RiskMatrixTableWrapper() {
  const { context } = useSecurityContext();
  const { data: risks = [] } = useRisksQuery(context);
  return <RiskMatrixTable risks={risks} />;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SecurityProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<RiskOverviewWrapper />} />
              <Route path="dashboard" element={<RiskOverviewWrapper />} />
              <Route path="risks" element={<RiskMatrixTableWrapper />} />
              <Route path="ingest" element={<DataIngestHub />} />
              <Route path="audit" element={<AuditConsole />} />
              <Route path="maintenance" element={<MaintenanceHub />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </SecurityProvider>
    </QueryClientProvider>
  );
}

export default App;
