import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClientModule } from '@angular/common/http';
import { PricingBreakdownComponent } from './pricing/pricing-breakdown.component';
import { FulfilmentTrackerComponent } from './fulfilment/fulfilment-tracker.component';

@NgModule({
  declarations: [PricingBreakdownComponent, FulfilmentTrackerComponent],
  imports: [CommonModule, HttpClientModule],
  exports: [PricingBreakdownComponent, FulfilmentTrackerComponent],
})
export class AcmestorefrontModule {}
