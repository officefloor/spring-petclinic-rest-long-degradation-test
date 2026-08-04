package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp01 required-fields: UPDATED by cp44 (address-structured) — Change the address to a structured form: the request now provides 'addressLine1', an optional 'addressLine2', 'city' and 'postcode', and the single flat 'address' input is removed */
@Tag("cp01")
class Cp01Tests extends AcceptanceBase {

	@Test
	void coreUpdatedBehaviour() throws Exception {
		// This rule changed. Change the address to a structured form: the request now provides 'addressLine1', an optional 'addressLine2', 'city' and 'postcode', and the single flat 'address' input is removed.
		// TODO: assert the UPDATED behaviour of "required-fields" under the new spec.
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}
