import { useCallback, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Badge,
  Page,
  Masthead,
  MastheadMain,
  MastheadBrand,
  MastheadContent,
  PageSidebar,
  PageSidebarBody,
  Nav,
  NavList,
  NavItem,
  PageSection,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
} from '@patternfly/react-core';
import { ThemeToggle } from '@components/theme-toggle';
import { KeyboardShortcutsHelp } from '@components/keyboard-shortcuts-help';
import { KeyboardShortcutsProvider } from '@providers/keyboard-shortcuts-context';
import { useKeyboardShortcuts } from '@hooks/use-keyboard-shortcuts';
import { useAwaitingApprovalCount } from '@features/incidents/hooks/use-awaiting-approval-count';
import { AppRoutes } from './routes';

function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { data: awaitingCount } = useAwaitingApprovalCount();
  const [isHelpOpen, setIsHelpOpen] = useState(false);

  const shortcuts = useMemo(
    () => ({
      '?': () => setIsHelpOpen((prev) => !prev),
    }),
    [],
  );

  useKeyboardShortcuts(shortcuts);

  const onNavSelect = useCallback(
    (_event: React.FormEvent<HTMLInputElement>, result: { itemId: number | string }) => {
      navigate(result.itemId as string);
    },
    [navigate],
  );

  const masthead = (
    <Masthead>
      <MastheadMain>
        <MastheadBrand>OpenShift AI Ops</MastheadBrand>
      </MastheadMain>
      <MastheadContent>
        <Toolbar>
          <ToolbarContent>
            <ToolbarItem>
              <ThemeToggle />
            </ToolbarItem>
          </ToolbarContent>
        </Toolbar>
      </MastheadContent>
    </Masthead>
  );

  const sidebar = (
    <PageSidebar>
      <PageSidebarBody>
        <Nav onSelect={onNavSelect} aria-label="Main navigation">
          <NavList>
            <NavItem itemId="/incidents" isActive={location.pathname.startsWith('/incidents')}>
              Incidents
              {awaitingCount != null && awaitingCount > 0 && (
                <>
                  {' '}
                  <Badge
                    isRead={false}
                    aria-label={`${awaitingCount} incidents awaiting approval`}
                  >
                    {awaitingCount}
                  </Badge>
                </>
              )}
            </NavItem>
            <NavItem itemId="/statistics" isActive={location.pathname.startsWith('/statistics')}>
              Statistics
            </NavItem>
          </NavList>
        </Nav>
      </PageSidebarBody>
    </PageSidebar>
  );

  return (
    <Page masthead={masthead} sidebar={sidebar}>
      <PageSection>
        <AppRoutes />
      </PageSection>
      <KeyboardShortcutsHelp isOpen={isHelpOpen} onClose={() => setIsHelpOpen(false)} />
    </Page>
  );
}

export function App() {
  return (
    <KeyboardShortcutsProvider>
      <AppShell />
    </KeyboardShortcutsProvider>
  );
}
