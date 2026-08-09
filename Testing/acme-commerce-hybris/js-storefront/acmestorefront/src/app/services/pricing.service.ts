import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { OccEndpointsService } from '@spartacus/core';

export interface PricingBreakdown {
  subtotal: number;
  spendDiscount: number;
  loyaltyDiscount: number;
  promoDiscount: number;
  total: number;
  appliedPromoCode?: string;
}

@Injectable({ providedIn: 'root' })
export class PricingService {
  constructor(
    private http: HttpClient,
    private occEndpoints: OccEndpointsService
  ) {}

  getBreakdown(orderCode: string, promoCode?: string): Observable<PricingBreakdown> {
    const url = this.occEndpoints.buildUrl('pricing/quote', {
      queryParams: { orderCode, promoCode },
    });
    return this.http.get<PricingBreakdown>(url);
  }
}
