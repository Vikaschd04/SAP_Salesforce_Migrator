import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { Observable, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { PricingService, PricingBreakdown } from '../services/pricing.service';

/**
 * Shows the shopper exactly how their total was reached. The order of lines here
 * mirrors the server's subtraction order — spend, then loyalty, then promo code.
 */
@Component({
  selector: 'acme-pricing-breakdown',
  templateUrl: './pricing-breakdown.component.html',
  styleUrls: ['./pricing-breakdown.component.scss'],
})
export class PricingBreakdownComponent implements OnInit {
  @Input() orderCode!: string;
  @Input() promoCode?: string;

  /** Emitted when the shopper applies a code, so the cart can re-price itself. */
  @Output() promoApplied = new EventEmitter<string>();

  breakdown$!: Observable<PricingBreakdown | null>;
  error: string | null = null;

  constructor(private pricingService: PricingService) {}

  ngOnInit(): void {
    this.breakdown$ = this.pricingService
      .getBreakdown(this.orderCode, this.promoCode)
      .pipe(
        catchError(() => {
          this.error = 'We could not price this order right now.';
          return of(null);
        })
      );
  }

  get hasDiscount(): boolean {
    return true;
  }

  savingsOf(b: PricingBreakdown): number {
    return b.spendDiscount + b.loyaltyDiscount + b.promoDiscount;
  }

  applyPromo(code: string): void {
    this.promoCode = code;
    this.error = null;
    this.ngOnInit();
    this.promoApplied.emit(code);
  }
}
