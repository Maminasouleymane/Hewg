import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  Analysis,
  AnalyzeRequest,
  ProgressEvent,
  StatusEvent,
} from '../../features/analyzer/models/analysis.model';

const API = '/api';

@Injectable({ providedIn: 'root' })
export class AnalysisService {
  private readonly http = inject(HttpClient);

  start(req: AnalyzeRequest) {
    return this.http.post<{ analysis_id: string; status: string }>(`${API}/analyze`, req);
  }

  get(id: string) {
    return this.http.get<Analysis>(`${API}/analyze/${id}`);
  }

  /** Wraps the SSE endpoint. Completes after `complete`/`error`; closes the socket on unsubscribe. */
  status(id: string): Observable<StatusEvent> {
    return new Observable((sub) => {
      const es = new EventSource(`${API}/analyze/${id}/status`);
      const finish = () => {
        es.close();
        sub.complete();
      };

      es.addEventListener('progress', (e) =>
        sub.next({ type: 'progress', data: JSON.parse((e as MessageEvent).data) as ProgressEvent }),
      );
      es.addEventListener('complete', () => {
        sub.next({ type: 'complete' });
        finish();
      });
      // The name "error" is shared with native connection errors; only server-sent ones carry data.
      es.addEventListener('error', (e) => {
        const data = (e as MessageEvent).data;
        if (data) {
          const parsed = JSON.parse(data) as { message: string; step?: string };
          sub.next({ type: 'error', ...parsed });
        } else {
          sub.next({ type: 'error', message: 'Lost connection to the forge. Please try again.' });
        }
        finish();
      });
      return () => es.close();
    });
  }
}
