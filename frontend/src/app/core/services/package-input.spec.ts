import { describe, expect, it } from 'vitest';
import { parsePackageInput } from './package-input';

describe('parsePackageInput', () => {
  it.each([
    ['rxjs', 'rxjs'],
    ['  RxJS  ', 'rxjs'],
    ['rxjs@7.8.0', 'rxjs'],
    ['@angular/core', '@angular/core'],
    ['@angular/core@17.0.0', '@angular/core'],
    ['npm i -D @types/node', '@types/node'],
    ['https://www.npmjs.com/package/rxjs', 'rxjs'],
    ['https://www.npmjs.com/package/rxjs/v/6.5.0', 'rxjs'],
    ['https://www.npmjs.com/package/@angular/core?activeTab=versions', '@angular/core'],
    ['www.npmjs.com/package/@angular/core/v/17.0.0', '@angular/core'],
    ['npmjs.com/package/lodash', 'lodash'],
    ['https://registry.npmjs.org/@scope%2fpkg', '@scope/pkg'],
    ['https://unpkg.com/react@18.2.0/index.js', 'react'],
    ['https://cdn.jsdelivr.net/npm/vue@3/dist/vue.js', 'vue'],
  ])('%s -> %s', (input, expected) => {
    expect(parsePackageInput(input)).toBe(expected);
  });

  it.each(['', '   ', 'not a package!', 'https://www.npmjs.com/'])('rejects %j', (input) => {
    expect(parsePackageInput(input)).toBe('');
  });
});
