import { Injectable, inject } from '@angular/core';
import { catchError, map, of } from 'rxjs';

import { HttpClient } from '@angular/common/http';

export interface PackageSuggestion {
  name: string;
  description?: string;
}

@Injectable({ providedIn: 'root' })
export class PackageService {
  private readonly http = inject(HttpClient);

  /** Versions newest-first; empty when the package can't be resolved. */
  versions(name: string) {
    return this.http
      .get<{ versions: string[] }>(`/api/packages/${name}/versions`)
      .pipe(
        map((r) => r.versions),
        catchError(() => of([] as string[])),
      );
  }

  /** Fuzzy name search via npm's own public registry search */
  search(query: string) {
    return this.http
      .get<{ objects: { package: PackageSuggestion }[] }>(
        'https://registry.npmjs.org/-/v1/search',
        { params: { text: query, size: 10 } },
      )
      .pipe(
        map((r) => r.objects.map((o) => o.package)),
        catchError(() => of([] as PackageSuggestion[])),
      );
  }
}
