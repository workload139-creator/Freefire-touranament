console.log("FF Tournament website loaded");


// Smooth scrolling

document
    .querySelectorAll('a[href^="#"]')
    .forEach(function(link) {

        link.addEventListener(
            "click",
            function(event) {

                const target =
                    document.querySelector(
                        this.getAttribute("href")
                    );

                if (target) {

                    event.preventDefault();

                    target.scrollIntoView({
                        behavior: "smooth"
                    });

                }

            }
        );

    });


// Registration message

document
    .querySelectorAll(".main-form")
    .forEach(function(form) {

        form.addEventListener(
            "submit",
            function() {

                console.log(
                    "Form submitted"
                );

            }
        );

    });
