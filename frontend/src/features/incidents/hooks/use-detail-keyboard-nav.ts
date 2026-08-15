import { useMemo, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useKeyboardShortcuts } from '@hooks/use-keyboard-shortcuts';

interface UseDetailKeyboardNavOptions {
  incidentState: string;
  expandedStage: number | null;
  stageCount: number;
  onStageSelect: (index: number) => void;
  onApprove?: () => void;
}

export function useDetailKeyboardNav({
  incidentState,
  expandedStage,
  stageCount,
  onStageSelect,
  onApprove,
}: UseDetailKeyboardNavOptions) {
  const navigate = useNavigate();
  const location = useLocation();
  const returnSearch = (location.state as { returnSearch?: string } | null)?.returnSearch ?? '';

  const goBack = useCallback(() => {
    navigate(`/incidents${returnSearch}`, {
      state: (location.state as { returnFocusIndex?: number } | null) ?? undefined,
    });
  }, [navigate, returnSearch, location.state]);

  const handleApprove = useCallback(() => {
    const remediationStageIndex = 3;
    if (
      incidentState === 'awaiting_approval' &&
      expandedStage === remediationStageIndex &&
      onApprove
    ) {
      onApprove();
    }
  }, [incidentState, expandedStage, onApprove]);

  const shortcuts = useMemo(() => {
    const map: Record<string, () => void> = {
      Escape: goBack,
      Backspace: goBack,
      a: handleApprove,
    };

    for (let i = 1; i <= Math.min(stageCount, 6); i++) {
      const stageIndex = i - 1;
      map[String(i)] = () => onStageSelect(stageIndex);
    }

    return map;
  }, [goBack, handleApprove, stageCount, onStageSelect]);

  useKeyboardShortcuts(shortcuts);
}
