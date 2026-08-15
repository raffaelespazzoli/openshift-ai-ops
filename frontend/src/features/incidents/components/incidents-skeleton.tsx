import {
  DataList,
  DataListItem,
  DataListItemRow,
  DataListItemCells,
  DataListCell,
} from '@patternfly/react-core';
import { Skeleton } from '@patternfly/react-core';

const SKELETON_ROWS = 8;

export function IncidentsSkeleton() {
  return (
    <DataList aria-label="Loading incidents">
      {Array.from({ length: SKELETON_ROWS }, (_, i) => (
        <DataListItem key={i} id={`skeleton-${i}`}>
          <DataListItemRow>
            <DataListItemCells
              dataListCells={[
                <DataListCell key="sev" width={1}>
                  <Skeleton width="60px" screenreaderText="Loading severity" />
                </DataListCell>,
                <DataListCell key="state" width={2}>
                  <Skeleton width="120px" screenreaderText="Loading state" />
                </DataListCell>,
                <DataListCell key="time" width={2}>
                  <Skeleton width="100px" screenreaderText="Loading time" />
                </DataListCell>,
                <DataListCell key="fp" width={1}>
                  <Skeleton width="70px" screenreaderText="Loading label" />
                </DataListCell>,
              ]}
            />
          </DataListItemRow>
        </DataListItem>
      ))}
    </DataList>
  );
}
