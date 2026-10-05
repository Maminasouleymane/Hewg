import { Pipe, PipeTransform } from '@angular/core';

/** 'NEW_FEATURE' -> 'New feature' */
@Pipe({ name: 'label' })
export class LabelPipe implements PipeTransform {
  transform(value: string): string {
    const s = value.replace(/_/g, ' ').toLowerCase();
    return s.charAt(0).toUpperCase() + s.slice(1);
  }
}
