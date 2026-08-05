package org.springframework.samples.petclinic.acceptance;

import java.time.DayOfWeek;
import java.time.LocalDate;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** cp47 holiday-business-day: the default registration date rolls past public holidays as well as
 *  weekends. The specific holiday calendar and the server clock can't be driven black-box, so assert
 *  the invariant that subsumes it: the default registrationDate is never a Saturday or Sunday. */
@Tag("cp47")
class Cp47Tests extends AcceptanceBase {

	@Test
	void coreDefaultDateIsBusinessDay() throws Exception {
		DayOfWeek dow = LocalDate.parse(
				fetchOwner(createOwnerOk(structuredOwner())).get("registrationDate").asText()).getDayOfWeek();
		assertTrue(dow != DayOfWeek.SATURDAY && dow != DayOfWeek.SUNDAY, dow.toString());
	}
}
