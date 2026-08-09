import { Component, Input, OnDestroy, OnInit } from '@angular/core';
import { Subscription, interval } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { FulfilmentService, FulfilmentSummary } from '../services/fulfilment.service';

/** Polls fulfilment state so the shopper sees progress without reloading. */
@Component({
  selector: 'acme-fulfilment-tracker',
  templateUrl: './fulfilment-tracker.component.html',
})
export class FulfilmentTrackerComponent implements OnInit, OnDestroy {
  @Input() orderCode!: string;

  summary: FulfilmentSummary | null = null;
  private sub?: Subscription;

  readonly steps = ['PENDING', 'ALLOCATED', 'PICKED', 'SHIPPED', 'DELIVERED'];

  constructor(private fulfilmentService: FulfilmentService) {}

  ngOnInit(): void {
    this.sub = interval(15000)
      .pipe(switchMap(() => this.fulfilmentService.getSummary(this.orderCode)))
      .subscribe((s) => (this.summary = s));
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  isReached(step: string): boolean {
    if (!this.summary) return false;
    return this.steps.indexOf(step) <= this.steps.indexOf(this.summary.state);
  }

  get isCancelled(): boolean {
    return this.summary?.state === 'CANCELLED';
  }
}
