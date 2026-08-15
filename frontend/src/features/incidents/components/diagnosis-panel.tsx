import {
  Alert,
  AlertActionLink,
  DescriptionList,
  DescriptionListGroup,
  DescriptionListTerm,
  DescriptionListDescription,
  Label,
  List,
  ListItem,
  ExpandableSection,
} from '@patternfly/react-core';
import { useState } from 'react';
import { ConfidenceBadge } from '@components/confidence-badge';
import type { DiagnosisData, IncidentDetail } from '@models/incident';

interface DiagnosisPanelProps {
  incident: IncidentDetail;
}

function formatTimestamp(iso?: string): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function DiagnosisContent({ diagnosis, label }: { diagnosis: DiagnosisData; label?: string }) {
  const [evidenceExpanded, setEvidenceExpanded] = useState(false);

  return (
    <div>
      {label && (
        <h4 style={{ marginBottom: 'var(--pf-t--global--spacer--sm)' }}>
          {label}
          {diagnosis.created_at && (
            <span
              style={{
                fontWeight: 'normal',
                fontSize: 'var(--pf-t--global--font--size--sm)',
                marginLeft: 'var(--pf-t--global--spacer--sm)',
                color: 'var(--pf-t--global--text--color--subtle)',
              }}
            >
              ({formatTimestamp(diagnosis.created_at)})
            </span>
          )}
        </h4>
      )}
      <DescriptionList>
        <DescriptionListGroup>
          <DescriptionListTerm>Root Cause</DescriptionListTerm>
          <DescriptionListDescription>
            <Label isCompact>{diagnosis.root_cause_code}</Label>
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Causal Chain</DescriptionListTerm>
          <DescriptionListDescription>
            <List isPlain component="ol">
              {diagnosis.causal_chain.map((step, i) => (
                <ListItem key={i}>{step}</ListItem>
              ))}
            </List>
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Affected Resources</DescriptionListTerm>
          <DescriptionListDescription>
            {diagnosis.affected_resources.join(', ') || 'None'}
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Evidence</DescriptionListTerm>
          <DescriptionListDescription>
            <ExpandableSection
              toggleText={evidenceExpanded ? 'Hide evidence' : `Show evidence (${diagnosis.evidence.length})`}
              isExpanded={evidenceExpanded}
              onToggle={(_event, expanded) => setEvidenceExpanded(expanded)}
            >
              <List isPlain>
                {diagnosis.evidence.map((e, i) => (
                  <ListItem key={i}>
                    <strong>{e.source}</strong>: {e.query} &rarr; {e.result}
                  </ListItem>
                ))}
                {diagnosis.evidence.length === 0 && <ListItem>No evidence artifacts</ListItem>}
              </List>
            </ExpandableSection>
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Agent Summary</DescriptionListTerm>
          <DescriptionListDescription>{diagnosis.agent_summary}</DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Confidence</DescriptionListTerm>
          <DescriptionListDescription>
            <ConfidenceBadge confidence={diagnosis.confidence} />
          </DescriptionListDescription>
        </DescriptionListGroup>
      </DescriptionList>
    </div>
  );
}

interface FastPathProceedProps {
  similarity: number | null;
  caseRecordId: string | null;
}

function FastPathProceedControl({ similarity, caseRecordId }: FastPathProceedProps) {
  return (
    <div style={{ marginTop: 'var(--pf-t--global--spacer--md)' }}>
      <Alert
        variant="info"
        isInline
        title="Fast-path match available"
        actionLinks={
          <AlertActionLink
            onClick={() => {
              window.dispatchEvent(
                new CustomEvent('fast-path-proceed', {
                  detail: { caseRecordId },
                }),
              );
            }}
          >
            Proceed with Fast-Path
          </AlertActionLink>
        }
      >
        A previous resolution with {similarity != null ? `${Math.round(similarity * 100)}% similarity` : 'a known match'} is available.
      </Alert>
    </div>
  );
}

export function DiagnosisPanel({ incident }: DiagnosisPanelProps) {
  const attempts = incident.diagnosis_attempts;
  const singleDiagnosis = incident.diagnosis;

  if (!singleDiagnosis && (!attempts || attempts.length === 0)) {
    const hasLlmFailure = incident.state === 'failed';
    const hasFastPath = incident.fast_path_similarity != null && incident.fast_path_case_record_id != null;

    if (hasLlmFailure && hasFastPath) {
      return (
        <div>
          <p>Diagnosis unavailable — LLM unreachable</p>
          <FastPathProceedControl
            similarity={incident.fast_path_similarity}
            caseRecordId={incident.fast_path_case_record_id}
          />
        </div>
      );
    }
    if (hasLlmFailure) {
      return <p>Diagnosis unavailable — LLM unreachable</p>;
    }
    return <p>Diagnosis data not yet available.</p>;
  }

  if (attempts && attempts.length > 1) {
    return (
      <div>
        {attempts.map((attempt, i) => {
          const isLast = i === attempts.length - 1;
          return (
            <div
              key={i}
              style={{
                marginBottom: 'var(--pf-t--global--spacer--md)',
                ...(isLast
                  ? {
                      borderLeft: '3px solid var(--pf-t--global--color--brand--default)',
                      paddingLeft: 'var(--pf-t--global--spacer--md)',
                    }
                  : {}),
              }}
            >
              <DiagnosisContent
                diagnosis={attempt}
                label={`Attempt ${i + 1}${isLast ? ' (accepted)' : ''}`}
              />
            </div>
          );
        })}
      </div>
    );
  }

  return <DiagnosisContent diagnosis={singleDiagnosis!} />;
}
