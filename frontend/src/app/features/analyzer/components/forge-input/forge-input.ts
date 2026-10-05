import { Component, DestroyRef, inject, output, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Subject, debounceTime, distinctUntilChanged, filter, switchMap, tap } from 'rxjs';
import { PackageService } from '../../../../core/services/package.service';
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

  readonly submitted = output<AnalyzeRequest>();

  protected name = '';
  protected from = '';
  protected to = '';
  protected readonly versions = signal<string[]>([]);
  /** Package whose versions are loaded (or being loaded); '' when none. */
  protected readonly resolved = signal('');
  protected readonly loading = signal(false);

  constructor() {
    this.lookups
      .pipe(
        debounceTime(350),
        distinctUntilChanged(),
        tap((pkg) => {
          this.resolved.set(pkg);
          this.versions.set([]);
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
    return !!(this.packageName && this.from.trim() && this.to.trim());
  }

  protected onNameChange(value: string) {
    this.name = value;
    this.lookups.next(parsePackageInput(value));
  }

  /** Replace a pasted link / spec with the bare package name. */
  protected normalizeName() {
    const pkg = this.packageName;
    if (pkg) this.name = pkg;
  }

  protected submit() {
    if (!this.valid) return;
    this.submitted.emit({
      package_name: this.packageName,
      from_version: this.from.trim(),
      to_version: this.to.trim(),
    });
  }
}
