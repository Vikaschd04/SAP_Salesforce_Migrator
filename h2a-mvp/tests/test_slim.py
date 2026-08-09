"""Prompt slimming: fewer bytes to the model, identical meaning.

Most of these are safety tests rather than savings tests. A slimmer that drops something
load-bearing fails invisibly — the run still succeeds, the reports still come out green,
and a business rule is simply gone. That is the one failure this product cannot afford,
so the bar for removing anything is that it *cannot* carry a rule.
"""

import textwrap

from src.slim import slim_java, slim_classes, enabled

MODEL = textwrap.dedent("""
    package de.hybris.platform.core.model.order;

    import de.hybris.platform.core.model.user.CustomerModel;
    import de.hybris.platform.core.model.c2l.CurrencyModel;
    import de.hybris.platform.servicelayer.model.ItemModel;
    import java.util.List;
    import java.math.BigDecimal;

    /**
     * An order. Orders above 5000 receive a 10 percent discount.
     */
    public class OrderModel extends ItemModel
    {
        private String code;
        private BigDecimal net;
        private BigDecimal totalTax;

        public String getCode()
        {
            return code;
        }

        public void setCode(String code)
        {
            this.code = code;
        }

        public BigDecimal getNet()
        {
            return net;
        }

        /**
         * Rejects a zero-value order — the rule that must never be lost.
         */
        public BigDecimal calculateTotal()
        {
            if (net == null)
            {
                throw new IllegalStateException("net is required");
            }
            return net.add(totalTax);
        }
    }
    """).strip()


def test_it_actually_saves_something():
    text, st = slim_java(MODEL)
    assert st["applied"] and st["saved_pct"] >= 10
    assert st["imports_removed"] == 5
    assert st["accessors_removed"] == 3


def test_business_logic_survives_verbatim():
    text, _ = slim_java(MODEL)
    assert "calculateTotal" in text
    assert 'throw new IllegalStateException("net is required")' in text
    assert "net.add(totalTax)" in text


def test_javadoc_survives():
    """On this codebase javadoc is a quarter of the bytes and it is where the rules are
    actually written down. Dropping it would be the most expensive mistake available."""
    text, _ = slim_java(MODEL)
    assert "Orders above 5000 receive a 10 percent discount" in text
    assert "the rule that must never be lost" in text


def test_a_computed_getter_is_not_treated_as_an_accessor():
    """`getTotal()` that computes something is business logic wearing an accessor's name."""
    src = MODEL.replace("""    public BigDecimal getNet()
    {
        return net;
    }""", """    public BigDecimal getNet()
    {
        if (net == null) { return BigDecimal.ZERO; }
        return net.multiply(RATE);
    }""")
    text, st = slim_java(src)
    assert "net.multiply(RATE)" in text
    assert st["accessors_removed"] == 2, "a computed getter was stripped as boilerplate"


def test_fields_are_kept():
    """The data model has to survive — it is what the SObject schema is derived from."""
    text, _ = slim_java(MODEL)
    for f in ("private String code;", "private BigDecimal net;", "private BigDecimal totalTax;"):
        assert f in text


def test_dependencies_are_still_stated_just_not_at_length():
    text, _ = slim_java(MODEL)
    assert "// imports:" in text
    assert "de.hybris.platform" in text
    assert "import de.hybris.platform.core.model.user.CustomerModel;" not in text


def test_braces_stay_balanced():
    text, _ = slim_java(MODEL)
    assert text.count("{") == text.count("}")


def test_a_small_class_is_left_alone():
    """Below a threshold there is nothing to win and the risk is all downside."""
    src = "public class Tiny { public int add(int a, int b) { return a + b; } }"
    text, st = slim_java(src)
    assert text == src and not st["applied"]


def test_a_class_with_nothing_to_trim_is_returned_untouched():
    src = "public class Big {\n" + "\n".join(
        f"    public int compute{i}(int x) {{ return x * {i} + 1; }}" for i in range(60)) + "\n}"
    text, st = slim_java(src)
    assert text == src and not st["applied"]


def test_angular_imports_are_handled_too():
    src = textwrap.dedent("""
        import { Component, OnInit } from '@angular/core';
        import { Observable } from 'rxjs';
        import { ProductService } from '../services/product.service';

        @Component({ selector: 'app-product-list', templateUrl: './product-list.component.html' })
        export class ProductListComponent implements OnInit {
          products$: Observable<Product[]>;
          constructor(private productService: ProductService) {}
          ngOnInit(): void {
            this.products$ = this.productService.getProducts();
          }
          filterInStock(items: Product[]): Product[] {
            return items.filter(p => p.stockLevel > 0 && p.active);
          }
        }
        """).strip() + "\n" + "// padding\n" * 60
    text, st = slim_java(src)
    assert st["applied"]
    assert "import { Component" not in text
    assert "p.stockLevel > 0 && p.active" in text, "component logic was dropped"


def test_slim_classes_reports_an_aggregate():
    out, st = slim_classes([{"class_name": "OrderModel", "source": MODEL},
                            {"class_name": "Tiny", "source": "class T {}"}])
    assert st["classes"] == 2 and st["slimmed"] == 1
    assert st["before"] > st["after"] and st["saved_pct"] > 0
    assert out[1]["source"] == "class T {}", "an untouched class must pass through unchanged"


def test_it_can_be_switched_off(monkeypatch):
    """So a run can be compared against the unslimmed baseline."""
    assert enabled({}) is True
    assert enabled({"prompts": {"slim": False}}) is False
    monkeypatch.setenv("H2A_SLIM_PROMPTS", "0")
    assert enabled({}) is False
