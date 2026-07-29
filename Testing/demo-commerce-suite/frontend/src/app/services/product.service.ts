import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

import { Product } from '../models/product.model';

/**
 * Reads the product catalogue from the commerce REST API.
 *
 * On Salesforce this backing data comes from the migrated `Product__c` SObject, so
 * these calls map to `@AuraEnabled(cacheable=true)` Apex controller methods.
 */
@Injectable({ providedIn: 'root' })
export class ProductService {
  private readonly baseUrl = '/occ/v2/products';

  constructor(private readonly http: HttpClient) {}

  /** All active products in the catalogue. */
  getProducts(): Observable<Product[]> {
    return this.http
      .get<{ products: Product[] }>(this.baseUrl)
      .pipe(map((res) => res.products.filter((p) => p.active)));
  }

  /** A single product by its business code. */
  getProduct(code: string): Observable<Product> {
    return this.http.get<Product>(`${this.baseUrl}/${encodeURIComponent(code)}`);
  }

  /** Free-text search over name + description, case-insensitive. */
  searchProducts(query: string): Observable<Product[]> {
    const term = (query || '').trim().toLowerCase();
    return this.getProducts().pipe(
      map((products) =>
        !term
          ? products
          : products.filter(
              (p) =>
                p.name.toLowerCase().includes(term) ||
                p.description.toLowerCase().includes(term),
            ),
      ),
    );
  }
}
