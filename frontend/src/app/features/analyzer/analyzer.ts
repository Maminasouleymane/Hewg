import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { Router } from '@angular/router';
import { AnalysisService } from '../../core/services/analysis.service';
import { ChangeCard } from './components/change-card/change-card';
import { ForgeInput } from './components/forge-input/forge-input';
import { LoadingProgress } from './components/loading-progress/loading-progress';
import { ResultsSummary } from './components/results-summary/results-summary';
import { Analysis, AnalyzeRequest, Category } from './models/analysis.model';

type View = 'input' | 'loading' | 'results';
type Filter = 'ALL' | 'BREAKING' | 'DEPRECATED' | 'NEW_FEATURE';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'ALL', label: 'All' },
  { key: 'BREAKING', label: 'Breaking' },
  { key: 'DEPRECATED', label: 'Deprecated' },
  { key: 'NEW_FEATURE', label: 'New' },
];

@Component({
  selector: 'app-analyzer',
  imports: [ForgeInput, LoadingProgress, ResultsSummary, ChangeCard],
  templateUrl: './analyzer.html',
  styleUrl: './analyzer.scss',
})
export class Analyzer {
  private readonly service = inject(AnalysisService);
  private readonly router = inject(Router);

  /** Bound from the `analysis/:id` route. */
  readonly id = input<string>();

  protected readonly filters = FILTERS;
  protected readonly view = signal<View>('input');
  protected readonly analysisId = signal<string | null>(null);
  protected readonly analysis = signal<Analysis | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly starting = signal(false);
  protected readonly filter = signal<Filter>('ALL');

  protected readonly visible = computed(() => {
    const f = this.filter();
    const changes = this.analysis()?.changes ?? [];
    return f === 'ALL' ? changes : changes.filter((c) => c.category === (f as Category));
  });

  constructor() {
    effect(() => {
      const id = this.id();
      if (id) this.open(id);
    });
  }

  protected forge(req: AnalyzeRequest) {
    this.error.set(null);
    this.starting.set(true);
    this.service.start(req).subscribe({
      next: (r) => {
        this.starting.set(false);
        this.router.navigate(['/analysis', r.analysis_id]);
      },
      error: (e: HttpErrorResponse) => {
        this.starting.set(false);
        this.error.set(e.error?.detail && typeof e.error.detail === 'string'
          ? e.error.detail
          : 'Could not reach the forge. Is the backend running?');
      },
    });
  }

  /** Load an analysis: results if done, progress stream if running, error if failed. */
  private open(id: string) {
    this.analysisId.set(id);
    this.error.set(null);
    this.service.get(id).subscribe({
      next: (a) => {
        if (a.status === 'completed') this.show(a);
        else if (a.status === 'failed') this.fail(a.error ?? 'Analysis failed');
        else this.view.set('loading');
      },
      error: () => this.fail('That analysis could not be found.'),
    });
  }

  protected onCompleted() {
    const id = this.analysisId();
    if (id) this.service.get(id).subscribe((a) => this.show(a));
  }

  protected fail(message: string) {
    this.error.set(message);
    this.view.set('input');
  }

  private show(a: Analysis) {
    this.analysis.set(a);
    this.filter.set('ALL');
    this.view.set('results');
  }

  protected reset() {
    this.router.navigate(['/']);
    this.analysis.set(null);
    this.analysisId.set(null);
    this.error.set(null);
    this.view.set('input');
  }
}
