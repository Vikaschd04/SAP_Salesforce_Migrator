import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { OccEndpointsService } from '@spartacus/core';

export interface FulfilmentSummary {
  orderCode: string;
  state: string;
  lastEventAt: string;
  warehouseCode?: string;
}

@Injectable({ providedIn: 'root' })
export class FulfilmentService {
  constructor(private http: HttpClient, private occEndpoints: OccEndpointsService) {}

  getSummary(orderCode: string): Observable<FulfilmentSummary> {
    return this.http.get<FulfilmentSummary>(
      this.occEndpoints.buildUrl(`pricing/orders/${orderCode}/fulfilment`)
    );
  }
}
