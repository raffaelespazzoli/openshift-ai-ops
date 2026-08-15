import { useState } from 'react';
import {
  Alert,
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  TextArea,
  Tooltip,
  Split,
  SplitItem,
} from '@patternfly/react-core';
import { useApproveIncident } from '../hooks/use-approve-incident';
import { useRejectIncident } from '../hooks/use-reject-incident';

interface ApprovalActionsProps {
  incidentId: string;
  planSummary?: string;
}

export function ApprovalActions({ incidentId, planSummary }: ApprovalActionsProps) {
  const [isRejectModalOpen, setIsRejectModalOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [reviewTimeRemaining, setReviewTimeRemaining] = useState<number | null>(null);

  const approveMutation = useApproveIncident(incidentId);
  const rejectMutation = useRejectIncident(incidentId);

  const handleApprove = () => {
    setReviewTimeRemaining(null);
    approveMutation.mutate(undefined, {
      onError: (error) => {
        if (error.code === 'CONFLICT' && error.detail?.review_time_remaining != null) {
          setReviewTimeRemaining(error.detail.review_time_remaining);
        }
      },
    });
  };

  const handleReject = () => {
    rejectMutation.mutate(
      { reason: rejectReason },
      {
        onSuccess: () => {
          setIsRejectModalOpen(false);
          setRejectReason('');
        },
      },
    );
  };

  const handleOpenRejectModal = () => {
    setRejectReason('');
    setIsRejectModalOpen(true);
  };

  const approveButton = (
    <Button
      variant="primary"
      onClick={handleApprove}
      isLoading={approveMutation.isPending}
      isDisabled={approveMutation.isPending || reviewTimeRemaining != null}
      aria-label="Approve remediation plan"
      aria-describedby={planSummary ? `plan-summary-${incidentId}` : undefined}
    >
      Approve
    </Button>
  );

  return (
    <div style={{ marginBottom: 'var(--pf-t--global--spacer--md)' }}>
      <Split hasGutter>
        <SplitItem>
          {reviewTimeRemaining != null ? (
            <Tooltip
              content={`Review time remaining: ${Math.ceil(reviewTimeRemaining)}s`}
              isVisible
            >
              {approveButton}
            </Tooltip>
          ) : (
            approveButton
          )}
        </SplitItem>
        <SplitItem>
          <Button
            variant="danger"
            onClick={handleOpenRejectModal}
            isDisabled={approveMutation.isPending || rejectMutation.isPending}
            aria-label="Reject remediation plan"
            aria-describedby={planSummary ? `plan-summary-${incidentId}` : undefined}
          >
            Reject
          </Button>
        </SplitItem>
      </Split>

      {planSummary && (
        <span id={`plan-summary-${incidentId}`} className="pf-v6-u-screen-reader">
          {planSummary}
        </span>
      )}

      {approveMutation.isError && !reviewTimeRemaining && (
        <Alert
          variant="danger"
          isInline
          title="Failed to approve remediation"
          actionClose={undefined}
          style={{ marginTop: 'var(--pf-t--global--spacer--sm)' }}
        >
          {approveMutation.error?.error ?? 'An unexpected error occurred.'}
          <Button variant="link" onClick={handleApprove} isInline>
            Retry
          </Button>
        </Alert>
      )}

      {reviewTimeRemaining != null && (
        <Alert
          variant="warning"
          isInline
          title={`Minimum review time has not elapsed (${Math.ceil(reviewTimeRemaining)}s remaining)`}
          style={{ marginTop: 'var(--pf-t--global--spacer--sm)' }}
        />
      )}

      <Modal
        variant={ModalVariant.small}
        isOpen={isRejectModalOpen}
        onClose={() => setIsRejectModalOpen(false)}
        aria-label="Reject remediation plan"
      >
        <ModalHeader title="Reject Remediation Plan" />
        <ModalBody>
          <TextArea
            aria-label="Rejection reason"
            value={rejectReason}
            onChange={(_ev, val) => setRejectReason(val)}
            isRequired
            placeholder="Explain why this remediation plan should not proceed..."
          />
          {rejectMutation.isError && (
            <Alert
              variant="danger"
              isInline
              title="Failed to reject remediation"
              style={{ marginTop: 'var(--pf-t--global--spacer--sm)' }}
            >
              {rejectMutation.error?.error ?? 'An unexpected error occurred.'}
            </Alert>
          )}
        </ModalBody>
        <ModalFooter>
          <Button
            variant="danger"
            onClick={handleReject}
            isDisabled={!rejectReason.trim() || rejectMutation.isPending}
            isLoading={rejectMutation.isPending}
          >
            Reject
          </Button>
          <Button variant="link" onClick={() => setIsRejectModalOpen(false)}>
            Cancel
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
