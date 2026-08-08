package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** required-fields: an owner must supply an address in EITHER form (addressLine1
 * or flat address) plus city. A structured owner with neither addressLine1 nor a flat address is
 * rejected; missing city is still rejected. */
@Tag("cp01")
class Cp01Tests extends AcceptanceBase {

	@Test
	void coreRejectsWhenNoAddressAtAll() throws Exception {
		ObjectNode o = structuredOwner();
		o.remove("addressLine1"); // structuredOwner carries no flat 'address' either
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void errorRejectsMissingCity() throws Exception {
		ObjectNode o = structuredOwner();
		o.remove("city");
		createOwner(o).andExpect(status().isBadRequest());
	}
}
