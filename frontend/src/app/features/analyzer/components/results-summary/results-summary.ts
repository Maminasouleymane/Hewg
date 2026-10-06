import { Component, computed, input, signal } from '@angular/core';

import { Analysis } from '../../models/analysis.model';

@Component({
  selector: 'app-results-summary',
  templateUrl: './results-summary.html',
  styleUrl: './results-summary.scss',
})
export class ResultsSummary {
  readonly analysis = input.required<Analysis>();
  protected readonly copied = signal(false);

  protected readonly badges = computed(() => {
    const a = this.analysis();
    return [
      { label: 'Breaking', count: a.total_breaking, cls: 'breaking' },
      { label: 'Deprecated', count: a.total_deprecated, cls: 'deprecated' },
      { label: 'New features', count: a.total_new_features, cls: 'new' },
      //TODO: BUGFIX count is not available in the Analysis model, so we need to calculate it from the changes array
      { label: 'Bug fixes', count: a.changes.filter((c) => c.category === 'BUGFIX').length, cls: 'bugfix' },
    ];
  });

  protected async copyMarkdown() {
    try {
      await navigator.clipboard.writeText(toMarkdown(this.analysis()));
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 1800);
    } catch {
      /* clipboard unavailable (insecure context / denied) */
    }
  }

  protected exportJson() {
    const a = this.analysis();
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(a, null, 2)], { type: 'application/json' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `hewg-${a.package_name.replace(/\W+/g, '-')}-${a.from_version}-to-${a.to_version}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }
}

export function toMarkdown(a: Analysis): string {
  const lines = [
    `# ${a.package_name} ${a.from_version} → ${a.to_version}`,
    '',
    a.summary ?? '',
    '',
    `**${a.total_breaking}** breaking · **${a.total_deprecated}** deprecated · **${a.total_new_features}** new features`,
  ];
  for (const c of a.changes) {
    lines.push('', `## [${c.category}/${c.severity}] ${c.title}`, '');
    if (c.affected_api) lines.push(`\`${c.affected_api}\``, '');
    lines.push(c.explanation);
    if (c.migration_action) lines.push('', `**Migration:** ${c.migration_action}`);
    if (c.before_code) lines.push('', '```ts', `// before`, c.before_code, '```');
    if (c.after_code) lines.push('', '```ts', `// after`, c.after_code, '```');
    lines.push('', `_Introduced in ${c.source_version}_`);
  }
  return lines.join('\n');
}
