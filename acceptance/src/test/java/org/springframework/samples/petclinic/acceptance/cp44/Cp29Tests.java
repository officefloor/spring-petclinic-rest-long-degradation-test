package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp29 postcode: UPDATED by cp44 (address-structured) — Change the address to a structured form: the request now provides 'addressLine1', an optional 'addressLine2', 'city' and 'postcode', and the single flat 'address' input is removed */
@Tag("cp29")
class Cp29Tests extends AcceptanceBase {

	@Test
	void coreUpdatedBehaviour() throws Exception {
		// This rule changed. Change the address to a structured form: the request now provides 'addressLine1', an optional 'addressLine2', 'city' and 'postcode', and the single flat 'address' input is removed.
		// TODO: assert the UPDATED behaviour of "postcode" under the new spec.
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}
