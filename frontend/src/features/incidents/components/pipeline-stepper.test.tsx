import { render, screen, fireEvent } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect, vi } from 'vitest';
import { PipelineStepper } from './pipeline-stepper';
import type { PipelineStageConfig } from '@models/incident';

expect.extend(toHaveNoViolations);

const defaultStages: PipelineStageConfig[] = [
  { id: 'triage', label: 'Triage', state: 'completed' },
  { id: 'diagnosis', label: 'Diagnosis', state: 'completed' },
  { id: 'skeptic', label: 'Skeptic', state: 'completed' },
  { id: 'remediation', label: 'Remediation', state: 'awaiting' },
  { id: 'execution', label: 'Execution', state: 'pending' },
  { id: 'outcome', label: 'Outcome', state: 'pending' },
];

describe('PipelineStepper', () => {
  it('renders 6 stages with correct labels', () => {
    render(
      <PipelineStepper stages={defaultStages} expandedStage={null} onStageClick={vi.fn()} />,
    );
    expect(screen.getByText('Triage')).toBeInTheDocument();
    expect(screen.getByText('Diagnosis')).toBeInTheDocument();
    expect(screen.getByText('Skeptic')).toBeInTheDocument();
    expect(screen.getByText('Remediation')).toBeInTheDocument();
    expect(screen.getByText('Execution')).toBeInTheDocument();
    expect(screen.getByText('Outcome')).toBeInTheDocument();
  });

  it('applies correct aria-labels with state', () => {
    render(
      <PipelineStepper stages={defaultStages} expandedStage={null} onStageClick={vi.fn()} />,
    );
    expect(screen.getByLabelText('Triage: completed')).toBeInTheDocument();
    expect(screen.getByLabelText('Remediation: awaiting approval')).toBeInTheDocument();
    expect(screen.getByLabelText('Execution: pending')).toBeInTheDocument();
  });

  it('calls onStageClick when a stage is clicked', () => {
    const onStageClick = vi.fn();
    render(
      <PipelineStepper stages={defaultStages} expandedStage={null} onStageClick={onStageClick} />,
    );
    fireEvent.click(screen.getByText('Diagnosis'));
    expect(onStageClick).toHaveBeenCalledWith(1);
  });

  it('renders all states correctly — active, failed, skipped', () => {
    const mixedStages: PipelineStageConfig[] = [
      { id: 'triage', label: 'Triage', state: 'completed' },
      { id: 'diagnosis', label: 'Diagnosis', state: 'active' },
      { id: 'skeptic', label: 'Skeptic', state: 'failed' },
      { id: 'remediation', label: 'Remediation', state: 'skipped' },
      { id: 'execution', label: 'Execution', state: 'pending' },
      { id: 'outcome', label: 'Outcome', state: 'pending' },
    ];
    render(
      <PipelineStepper stages={mixedStages} expandedStage={null} onStageClick={vi.fn()} />,
    );
    expect(screen.getByLabelText('Diagnosis: in progress')).toBeInTheDocument();
    expect(screen.getByLabelText('Skeptic: failed')).toBeInTheDocument();
    expect(screen.getByLabelText('Remediation: skipped')).toBeInTheDocument();
  });

  it('renders skipped stage with disabled class', () => {
    const skippedStages: PipelineStageConfig[] = [
      { id: 'triage', label: 'Triage', state: 'completed' },
      { id: 'diagnosis', label: 'Diagnosis', state: 'skipped' },
      { id: 'skeptic', label: 'Skeptic', state: 'skipped' },
      { id: 'remediation', label: 'Remediation', state: 'skipped' },
      { id: 'execution', label: 'Execution', state: 'active' },
      { id: 'outcome', label: 'Outcome', state: 'pending' },
    ];
    const { container } = render(
      <PipelineStepper stages={skippedStages} expandedStage={null} onStageClick={vi.fn()} />,
    );
    const disabledSteps = container.querySelectorAll('.pf-m-disabled');
    expect(disabledSteps.length).toBe(3);
  });

  it('supports arrow key navigation between stages', () => {
    const onStageClick = vi.fn();
    render(
      <PipelineStepper stages={defaultStages} expandedStage={null} onStageClick={onStageClick} />,
    );

    const firstStep = screen.getByLabelText('Triage: completed');
    firstStep.focus();

    fireEvent.keyDown(firstStep.closest('[role="tablist"]')!, { key: 'ArrowRight' });
    expect(document.activeElement).toHaveAttribute('aria-label', 'Diagnosis: completed');

    fireEvent.keyDown(firstStep.closest('[role="tablist"]')!, { key: 'ArrowLeft' });
    expect(document.activeElement).toHaveAttribute('aria-label', 'Triage: completed');
  });

  it('supports Home/End key navigation', () => {
    render(
      <PipelineStepper stages={defaultStages} expandedStage={null} onStageClick={vi.fn()} />,
    );

    const container = screen.getByRole('tablist');
    fireEvent.keyDown(container, { key: 'End' });
    expect(document.activeElement).toHaveAttribute('aria-label', 'Outcome: pending');

    fireEvent.keyDown(container, { key: 'Home' });
    expect(document.activeElement).toHaveAttribute('aria-label', 'Triage: completed');
  });

  it('activates stage on Enter key', () => {
    const onStageClick = vi.fn();
    render(
      <PipelineStepper stages={defaultStages} expandedStage={null} onStageClick={onStageClick} />,
    );

    const container = screen.getByRole('tablist');
    fireEvent.keyDown(container, { key: 'Enter' });
    expect(onStageClick).toHaveBeenCalledWith(0);
  });

  it('renders role="tab" on each stage', () => {
    render(
      <PipelineStepper stages={defaultStages} expandedStage={null} onStageClick={vi.fn()} />,
    );
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(6);
  });

  it('sets aria-selected on expanded stage', () => {
    render(
      <PipelineStepper stages={defaultStages} expandedStage={2} onStageClick={vi.fn()} />,
    );
    const tabs = screen.getAllByRole('tab');
    expect(tabs[2]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[0]).toHaveAttribute('aria-selected', 'false');
  });

  it('renders aria-live status region', () => {
    render(
      <PipelineStepper stages={defaultStages} expandedStage={null} onStageClick={vi.fn()} />,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <PipelineStepper stages={defaultStages} expandedStage={null} onStageClick={vi.fn()} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
