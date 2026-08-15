import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
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
import { AppRoutes } from './routes';

export function App() {
  const location = useLocation();
  const navigate = useNavigate();

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
    </Page>
  );
}
