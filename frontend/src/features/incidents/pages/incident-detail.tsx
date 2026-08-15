import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useLocation, Link } from 'react-router-dom';
import {
  Breadcrumb,
  BreadcrumbItem,
  EmptyState,
  EmptyStateBody,
  EmptyStateFooter,
  EmptyStateActions,
  Button,
  Label,
  Skeleton,
  Title,
} from '@patternfly/react-core';
import { ExclamationCircleIcon } from '@patternfly/react-icons';
import SearchIcon from '@patternfly/react-icons/dist/esm/icons/search-icon';
import { useIncidentDetail } from '../hooks/use-incident-detail';
import { useIncidentSSE } from '../hooks/use-incident-sse';
import { getStageStates } from '@utils/pipeline-stages';
import { PipelineStepper } from '../components/pipeline-stepper';
import { StagePanel } from '../components/stage-panel';
import { TriagePanel } from '../components/triage-panel';
import { DiagnosisPanel } from '../components/diagnosis-panel';
import { SkepticPanel } from '../components/skeptic-panel';
import { RemediationPanel } from '../components/remediation-panel';
import { ExecutionPanel } from '../components/execution-panel';
import { OutcomePanel } from '../components/outcome-panel';

const TERMINAL_STATES = new Set(['resolved', 'failed', 'cancelled']);

export default function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const returnSearch = (location.state as { returnSearch?: string } | null)?.returnSearch ?? '';

  const { connectionState } = useIncidentSSE({ incidentId: id, enabled: !!id });
  const isSSEDisconnected = connectionState === 'disconnected';

  const [isTerminal, setIsTerminal] = useState(false);

  const shouldPoll = isSSEDisconnected && !isTerminal;

  const { data: incident, isPending, error, refetch } = useIncidentDetail(id!, {
    refetchInterval: shouldPoll ? 5000 : false,
  });

  useEffect(() => {
    if (incident) {
      setIsTerminal(TERMINAL_STATES.has(incident.state));
    }
  }, [incident]);

  const stages = useMemo(() => (incident ? getStageStates(incident) : []), [incident]);

  const [expandedStage, setExpandedStage] = useState<number | null>(null);

  useEffect(() => {
    if (stages.length === 0) return;
    const activeIndex = stages.findIndex(
      (s) => s.state === 'active' || s.state === 'awaiting',
    );
    if (activeIndex !== -1) setExpandedStage(activeIndex);
  }, [stages]);

  const handleStageClick = useCallback((index: number) => {
    setExpandedStage((prev) => (prev === index ? null : index));
  }, []);

  if (isPending) {
    return (
      <div aria-label="Loading incident detail" aria-busy="true">
        <Skeleton width="40%" height="24px" style={{ marginBottom: '16px' }} aria-label="Breadcrumb loading" />
        <Skeleton width="60%" height="32px" style={{ marginBottom: '24px' }} aria-label="Title loading" />
        <Skeleton width="100%" height="60px" style={{ marginBottom: '16px' }} aria-label="Pipeline loading" />
        <Skeleton width="100%" height="200px" aria-label="Content loading" />
      </div>
    );
  }

  const httpStatus = (error as Error & { status?: number })?.status;

  if (error && httpStatus === 404) {
    return (
      <EmptyState headingLevel="h2" icon={SearchIcon} titleText="Incident not found">
        <EmptyStateBody>
          The incident you are looking for does not exist or has been removed.
        </EmptyStateBody>
        <EmptyStateFooter>
          <EmptyStateActions>
            <Button variant="primary" component={(props) => <Link {...props} to={`/incidents${returnSearch}`} />}>
              Back to Incidents
            </Button>
          </EmptyStateActions>
        </EmptyStateFooter>
      </EmptyState>
    );
  }

  if (error) {
    return (
      <EmptyState headingLevel="h2" icon={ExclamationCircleIcon} titleText="Error loading incident" status="danger">
        <EmptyStateBody>
          An error occurred while loading the incident. Please try again.
        </EmptyStateBody>
        <EmptyStateFooter>
          <EmptyStateActions>
            <Button variant="primary" onClick={() => refetch()}>
              Retry
            </Button>
          </EmptyStateActions>
        </EmptyStateFooter>
      </EmptyState>
    );
  }

  if (!incident) return null;

  const alertName =
    incident.alerts[0]?.labels['alertname'] ?? `Incident ${incident.id}`;
  const isExecutionFailed = incident.execution_log?.status === 'failed';
  const hasRollbackPlan =
    (incident.remediation_plan?.rollback_plan?.length ?? 0) > 0;

  return (
    <div>
      <Breadcrumb>
        <BreadcrumbItem>
          <Link to={`/incidents${returnSearch}`}>Incidents</Link>
        </BreadcrumbItem>
        <BreadcrumbItem isActive>{alertName}</BreadcrumbItem>
      </Breadcrumb>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--pf-t--global--spacer--sm)',
          marginTop: 'var(--pf-t--global--spacer--md)',
          marginBottom: 'var(--pf-t--global--spacer--lg)',
        }}
      >
        <Title headingLevel="h1">{alertName}</Title>
        {incident.fast_path && (
          <Label isCompact color="blue">
            Fast-Path{incident.fast_path_similarity != null
              ? ` (${Math.round(incident.fast_path_similarity * 100)}%)`
              : ''}
          </Label>
        )}
        {shouldPoll && (
          <Label isCompact variant="outline" role="status" aria-live="polite">
            Live updates paused
          </Label>
        )}
      </div>

      <div style={{ marginBottom: 'var(--pf-t--global--spacer--lg)' }}>
        <PipelineStepper
          stages={stages}
          expandedStage={expandedStage}
          onStageClick={handleStageClick}
        />
      </div>

      {stages.map((stage, index) => (
        <StagePanel
          key={stage.id}
          stageId={stage.id}
          stageLabel={stage.label}
          isExpanded={expandedStage === index}
        >
          {stage.id === 'triage' && <TriagePanel incident={incident} />}
          {stage.id === 'diagnosis' && <DiagnosisPanel incident={incident} />}
          {stage.id === 'skeptic' && <SkepticPanel data={incident.skeptic_verdict} />}
          {stage.id === 'remediation' && (
            <RemediationPanel
              data={incident.remediation_plan}
              incidentId={incident.id}
              incidentState={incident.state}
            />
          )}
          {stage.id === 'execution' && (
            <ExecutionPanel
              data={incident.execution_log}
              hasRollbackPlan={hasRollbackPlan}
            />
          )}
          {stage.id === 'outcome' && (
            <OutcomePanel data={incident.outcome} isFailed={isExecutionFailed} />
          )}
        </StagePanel>
      ))}
    </div>
  );
}
