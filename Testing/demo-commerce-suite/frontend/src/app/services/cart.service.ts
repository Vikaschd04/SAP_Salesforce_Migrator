import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

import { Product, CartItem } from '../models/product.model';

/**
 * Client-side cart state. Holds the line items, exposes the running total, and
 * enforces the same rules the storefront relies on (positive quantity, stock cap).
 *
 * On Salesforce the cart lives in the component/state; checkout hands off to the
 * migrated `OrderService` Apex to place the order.
 */
@Injectable({ providedIn: 'root' })
export class CartService {
  private readonly items$ = new BehaviorSubject<CartItem[]>([]);

  /** Observable stream of the current cart lines. */
  getItems(): Observable<CartItem[]> {
    return this.items$.asObservable();
  }

  /** Add (or increment) a product line, capped at available stock. */
  addItem(product: Product, quantity: number): void {
    if (quantity <= 0) {
      throw new Error('Quantity must be greater than zero');
    }
    const items = [...this.items$.value];
    const existing = items.find((i) => i.product.code === product.code);
    const desired = (existing ? existing.quantity : 0) + quantity;
    const capped = Math.min(desired, product.stockLevel);
    if (existing) {
      existing.quantity = capped;
    } else {
      items.push({ product, quantity: capped });
    }
    this.items$.next(items);
  }

  /** Remove a product line entirely. */
  removeItem(productCode: string): void {
    this.items$.next(this.items$.value.filter((i) => i.product.code !== productCode));
  }

  /** Sum of quantity × price across every line. */
  getTotal(): number {
    return this.items$.value.reduce(
      (total, item) => total + item.product.price * item.quantity,
      0,
    );
  }

  /** Empty the cart (e.g. after a successful checkout). */
  clear(): void {
    this.items$.next([]);
  }
}
