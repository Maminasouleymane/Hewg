import { describe, expect, it } from 'vitest';
import { Analysis } from '../../models/analysis.model';
import { toMarkdown } from './results-summary';

describe('toMarkdown', () => {
  it('renders header, counts and diff blocks', () => {
    const md = toMarkdown({
      package_name: 'rxjs', from_version: '6.5.0', to_version: '7.8.0', summary: 'Moderate.',
      total_breaking: 1, total_deprecated: 0, total_new_features: 0,
      changes: [{
        id: '1', category: 'BREAKING', severity: 'CRITICAL', title: 'toPromise removed',
        affected_api: 'Observable.toPromise', explanation: 'Removed.', migration_action: 'Use lastValueFrom',
        before_code: 'x.toPromise()', after_code: 'lastValueFrom(x)', source_version: '7.0.0',
        reasoning: '', doc_reference: '',
      }],
    } as unknown as Analysis);
    expect(md).toContain('# rxjs 6.5.0 → 7.8.0');
    expect(md).toContain('## [BREAKING/CRITICAL] toPromise removed');
    expect(md).toContain('lastValueFrom(x)');
  });
});
