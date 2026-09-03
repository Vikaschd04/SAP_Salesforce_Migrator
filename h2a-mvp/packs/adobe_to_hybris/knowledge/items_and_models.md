# items.xml, and the models the platform writes for you

A Hybris data model is **declared at build time** in `<extension>-items.xml`. The platform
build then generates a Java model class per item type — `AcmeLoyaltyAccountModel`,
`OrderModel`. You never write those, and you must not: the build overwrites them.

```xml
<itemtype code="AcmeLoyaltyAccount" extends="GenericItem"
          autocreate="true" generate="true">
    <deployment table="acmeloyaltyaccount" typecode="10001"/>
    <attributes>
        <attribute qualifier="code" type="java.lang.String">
            <persistence type="property"/>
            <modifiers optional="false" unique="true"/>
        </attribute>
    </attributes>
</itemtype>
```

Typecodes above 10000 are customer territory; below is the platform's, and a collision
there is a platform conflict rather than a merge.

## Extending a type SAP already owns

This is the shape a Magento **EAV attribute** takes, and it is not the same declaration:

```xml
<itemtype code="Customer" autocreate="false" generate="false">
    <attributes>
        <attribute qualifier="acmeLoyaltyTier" type="java.lang.String">
            <persistence type="property"/>
        </attribute>
    </attributes>
</itemtype>
```

`autocreate="false" generate="false"` means *contribute to the existing type*. Declaring
`Customer` as a new type instead produces a second Customer holding half a customer — it
deploys cleanly, and the original stays authoritative and missing the fields.

## What items.xml cannot carry

Attribute **values**. A Magento EAV attribute is a database row created when a data patch
runs, and every value of it lives in the customer's database — as do any attributes added
through the admin UI, which appear in no file at all. The declaration migrates; the data
is an export.
