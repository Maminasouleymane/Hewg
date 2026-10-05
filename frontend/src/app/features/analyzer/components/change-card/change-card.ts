import { Component, computed, input } from '@angular/core';
import { LabelPipe } from '../../../../shared/pipes/labels.pipe';
import { Change } from '../../models/analysis.model';

@Component({
  selector: 'app-change-card',
  imports: [LabelPipe],
  templateUrl: './change-card.html',
  styleUrl: './change-card.scss',
  host: { '[style.animation-delay.s]': 'index() * 0.06' },
})
export class ChangeCard {
  readonly change = input.required<Change>();
  readonly index = input(0);

  protected readonly beforeLines = computed(() => lines(this.change().before_code));
  protected readonly afterLines = computed(() => lines(this.change().after_code));
}

const lines = (code: string | null) => (code ? code.split('\n') : []);
