import { Component, DestroyRef, computed, inject, output, signal } from '@angular/core';
import { rxResource, takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Subject, debounceTime, distinctUntilChanged, filter, switchMap, tap } from 'rxjs';
import { PackageService, PackageSuggestion } from '../../../../core/services/package.service';
import { parsePackageInput } from '../../../../core/services/package-input';
import { AnalyzeRequest } from '../../models/analysis.model';

@Component({
  selector: 'app-forge-input',
  imports: [FormsModule],
  templateUrl: './forge-input.html',
  styleUrl: './forge-input.scss',
})
export class ForgeInput {
  private readonly packages = inject(PackageService);
  private readonly lookups = new Subject<string>();
  private readonly queries = new Subject<string>();

  readonly submitted = output<AnalyzeRequest>();

  protected name = '';
  protected readonly from = signal('');
  protected readonly to = signal('');
  protected readonly versions = signal<string[]>([]);
  /** Package whose versions are loaded (or being loaded); '' when none. */
  protected readonly resolved = signal('');
  protected readonly loading = signal(false);
  protected readonly showSuggestions = signal(false);

  /** Debounced raw search text, bridged to a signal so `suggestions` can react to it. */
  private readonly query = toSignal(
    this.queries.pipe(debounceTime(250), distinctUntilChanged()),
    { initialValue: '' },
  );

  /** Fuzzy name suggestions from npm's search API; idle (no request) below 2 characters. */
  protected readonly suggestions = rxResource({
    params: () => (this.query().trim().length > 1 ? this.query().trim() : undefined),
    stream: ({ params }) => this.packages.search(params),
    defaultValue: [] as PackageSuggestion[],
  });

  /** Versions newer than `from` - versions() is newest-first, so that's everything before its index. */
  protected readonly toOptions = computed(() => {
    const list = this.versions();
    const idx = list.indexOf(this.from());
    return idx === -1 ? [] : list.slice(0, idx);
  });

  constructor() {
    this.lookups
      .pipe(
        debounceTime(350),
        distinctUntilChanged(),
        tap((pkg) => {
          this.resolved.set(pkg);
          this.versions.set([]);
          this.from.set('');
          this.to.set('');
        }),
        filter(Boolean),
        tap(() => this.loading.set(true)),
        switchMap((pkg) => this.packages.versions(pkg)),
        takeUntilDestroyed(inject(DestroyRef)),
      )
      .subscribe((v) => {
        this.loading.set(false);
        this.versions.set(v);
      });
  }

  protected get packageName() {
    return parsePackageInput(this.name);
  }

  protected get valid() {
    return !!(this.packageName && this.from().trim() && this.to().trim());
  }

  protected onNameChange(value: string) {
    this.name = value;
    this.showSuggestions.set(true);
    this.queries.next(value);
    this.lookups.next(parsePackageInput(value));
  }

  protected selectSuggestion(pkg: PackageSuggestion) {
    this.name = pkg.name;
    this.showSuggestions.set(false);
    this.lookups.next(pkg.name);
  }

  /** Closing on blur needs a short delay - a suggestion's (mousedown) prevents the blur
   *  that would otherwise fire before its (click) handler runs, but this still covers
   *  clicking away entirely (outside the field and the dropdown). */
  protected onBlur() {
    setTimeout(() => this.showSuggestions.set(false), 150);
  }

  /** Replace a pasted link / spec with the bare package name. */
  protected normalizeName() {
    const pkg = this.packageName;
    if (pkg) this.name = pkg;
  }

  protected onFromChange(value: string) {
    this.from.set(value);
    this.to.set(''); // a new "from" can invalidate the previously selected "to"
  }

  protected submit() {
    if (!this.valid) return;
    this.submitted.emit({
      package_name: this.packageName,
      from_version: this.from().trim(),
      to_version: this.to().trim(),
    });
  }
}
