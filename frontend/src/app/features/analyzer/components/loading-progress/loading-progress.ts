import { Component, DestroyRef, inject, input, output, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AnalysisService } from '../../../../core/services/analysis.service';

@Component({
  selector: 'app-loading-progress',
  templateUrl: './loading-progress.html',
  styleUrl: './loading-progress.scss',
})
export class LoadingProgress {
  private readonly service = inject(AnalysisService);
  private readonly destroyRef = inject(DestroyRef);

  readonly analysisId = input.required<string>();
  readonly completed = output<void>();
  readonly failed = output<string>();

  protected readonly message = signal('Heating the forge…');
  protected readonly progress = signal(3);

  ngOnInit() {
    this.service
      .status(this.analysisId())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((e) => {
        if (e.type === 'progress') {
          this.message.set(e.data.message);
          this.progress.set(e.data.progress);
        } else if (e.type === 'complete') {
          this.progress.set(100);
          this.completed.emit();
        } else {
          this.failed.emit(e.message);
        }
      });
  }
}
