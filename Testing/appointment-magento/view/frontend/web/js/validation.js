define([
    'jquery',
    'jquery/ui',
    'jquery/validate',
    'mage/translate'
    ], function($){
        'use strict';
        return function() {
            $.validator.addMethod(
                "validateMobile",
                function(value) {
                    if (value != "") {
                        return value.match(/^([+]\d{2})?\d{10}$/);
                    }
                    else {
                        return true;
                    }
                },
                $.mage.__("Please enter valid 10 digit mobile number")
            );
    }
});