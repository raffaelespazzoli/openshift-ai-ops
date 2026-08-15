import { useContext } from 'react';
import {
  DescriptionList,
  DescriptionListGroup,
  DescriptionListTerm,
  DescriptionListDescription,
  Modal,
  ModalBody,
  ModalHeader,
  ModalVariant,
  Switch,
} from '@patternfly/react-core';
import { KeyboardShortcutsContext } from '@providers/keyboard-shortcuts-context';

interface KeyboardShortcutsHelpProps {
  isOpen: boolean;
  onClose: () => void;
}

export function KeyboardShortcutsHelp({ isOpen, onClose }: KeyboardShortcutsHelpProps) {
  const { shortcutsEnabled, toggleShortcuts } = useContext(KeyboardShortcutsContext);

  return (
    <Modal
      variant={ModalVariant.medium}
      isOpen={isOpen}
      onClose={onClose}
      aria-label="Keyboard shortcuts"
    >
      <ModalHeader title="Keyboard Shortcuts" />
      <ModalBody>
        <div style={{ marginBottom: 'var(--pf-t--global--spacer--md)' }}>
          <Switch
            id="shortcuts-toggle"
            label="Enable keyboard shortcuts"
            isChecked={shortcutsEnabled}
            onChange={toggleShortcuts}
          />
        </div>
        <DescriptionList isHorizontal>
          <DescriptionListGroup>
            <DescriptionListTerm>j / k</DescriptionListTerm>
            <DescriptionListDescription>Navigate down / up in incident list</DescriptionListDescription>
          </DescriptionListGroup>
          <DescriptionListGroup>
            <DescriptionListTerm>Enter</DescriptionListTerm>
            <DescriptionListDescription>Open selected incident</DescriptionListDescription>
          </DescriptionListGroup>
          <DescriptionListGroup>
            <DescriptionListTerm>Esc / Backspace</DescriptionListTerm>
            <DescriptionListDescription>Return to incident list</DescriptionListDescription>
          </DescriptionListGroup>
          <DescriptionListGroup>
            <DescriptionListTerm>1 – 6</DescriptionListTerm>
            <DescriptionListDescription>Jump to pipeline stage</DescriptionListDescription>
          </DescriptionListGroup>
          <DescriptionListGroup>
            <DescriptionListTerm>a</DescriptionListTerm>
            <DescriptionListDescription>Approve remediation (when awaiting)</DescriptionListDescription>
          </DescriptionListGroup>
          <DescriptionListGroup>
            <DescriptionListTerm>?</DescriptionListTerm>
            <DescriptionListDescription>Show this help</DescriptionListDescription>
          </DescriptionListGroup>
        </DescriptionList>
      </ModalBody>
    </Modal>
  );
}
