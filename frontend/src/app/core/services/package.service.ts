import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { catchError, map, of } from 'rxjs';

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
}
